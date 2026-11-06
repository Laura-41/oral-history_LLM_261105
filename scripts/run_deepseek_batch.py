#!/usr/bin/env python3
"""按批次运行 DeepSeek 全链路并生成熔断汇总。

链路：窗口抽取 → 文档级输入准备 → 文档级归并 → 技术汇总。
默认模型 cuc/deepseek，结果写入按模型隔离的目录，不覆盖 Qwen 与首批结果。
任一子步骤失败即停止，不自动进入下一批。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
BATCH_ROOT = PROJECT_DIR / "04_54份正式语料批处理"
STAGE_ROOT = BATCH_ROOT / "document_consolidation"
PYTHON = sys.executable

MODEL_PRICE_PER_MILLION = {
    "cuc/deepseek": (1.0, 4.0),
    "cuc/qwen": (3.0, 18.0),
}

MODEL_TIMEOUTS = {
    "cuc/deepseek": (600, 900),
    "cuc/qwen": (1800, 2400),
}


def prices_for(model: str) -> tuple[float, float]:
    """每百万 Token 的输入／输出单价（元）；未知模型回退到 DeepSeek 档。"""
    return MODEL_PRICE_PER_MILLION.get(
        model, MODEL_PRICE_PER_MILLION["cuc/deepseek"]
    )


def timeouts_for(model: str) -> tuple[int, int]:
    """窗口级／文档级超时秒数；未知模型回退到 DeepSeek 档。"""
    return MODEL_TIMEOUTS.get(model, MODEL_TIMEOUTS["cuc/deepseek"])


def safe_model_name(model: str) -> str:
    return model.replace("/", "_")


def run_track_for(model: str) -> str:
    """运行线标记按模型生成；DeepSeek 保持原值，兼容既有汇总文件。"""
    if model == "cuc/deepseek":
        return "DEEPSEEK_PARALLEL_TRACK"
    if model == "cuc/qwen":
        return "QWEN_MAIN_TRACK"
    return f"{safe_model_name(model).upper()}_TRACK"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def usage_parts(record: dict[str, Any]) -> dict[str, int]:
    usage = record.get("usage") or {}
    return {
        "input": int(usage.get("prompt_tokens") or 0),
        "output": int(usage.get("completion_tokens") or 0),
        "total": int(usage.get("total_tokens") or 0),
    }


def run_step(command: list[str], label: str) -> int:
    print(f"\n=== {label} ===", flush=True)
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=str(PROJECT_DIR), check=False)
    if result.returncode != 0:
        print(
            f"步骤失败（退出码 {result.returncode}）：{label}；按熔断规则停止本批。",
            file=sys.stderr,
            flush=True,
        )
    return result.returncode


def summarize(
    batch: str,
    model: str,
    documents: list[dict[str, Any]],
    expected_windows: dict[str, int],
) -> dict[str, Any]:
    model_dir = safe_model_name(model)
    window_root = BATCH_ROOT / "validated_json" / model_dir
    raw_root = BATCH_ROOT / "raw_responses" / model_dir
    queue_root = BATCH_ROOT / "review_queue" / model_dir
    document_root = STAGE_ROOT / "validated_json" / model_dir

    per_document: list[dict[str, Any]] = []
    token_input = 0
    token_output = 0
    validation_error_details: list[str] = []

    for document in documents:
        technical_id = document["technical_document_id"]
        window_paths = sorted(window_root.glob(f"{technical_id}-W*.json"))
        passed_windows = 0
        candidate_count = 0
        edge_count = 0
        coverage_ok = True
        for path in window_paths:
            record = read_json(path)
            usage = usage_parts(record)
            token_input += usage["input"]
            token_output += usage["output"]
            if record.get("technical_passed"):
                passed_windows += 1
            metrics = record.get("metrics") or {}
            candidate_count += int(metrics.get("event_count") or 0)
            if metrics.get("all_input_segments_accounted_for") is not True:
                coverage_ok = False
            edge_count += len(record.get("edge_candidate_ids") or [])
            for error in record.get("validation_errors") or []:
                validation_error_details.append(f"{path.name}: {error}")

        raw_files = list(raw_root.glob(f"*_{technical_id}-W*.json")) if raw_root.exists() else []
        queue_path = queue_root / f"{technical_id}.json"
        queue_pairs = 0
        terminal_ids = 0
        if queue_path.exists():
            queue = read_json(queue_path)
            queue_pairs = len(queue.get("adjacent_candidate_pairs") or [])
            terminal_ids = len(queue.get("terminal_candidate_ids") or [])

        document_path = document_root / f"{technical_id}.json"
        document_result: dict[str, Any] = {
            "exists": document_path.exists(),
            "technical_passed": False,
            "document_event_count": 0,
            "personal": 0,
            "context": 0,
            "uncertain": 0,
            "needs_review": 0,
        }
        if document_path.exists():
            record = read_json(document_path)
            usage = usage_parts(record)
            token_input += usage["input"]
            token_output += usage["output"]
            metrics = record.get("metrics") or {}
            document_result.update(
                {
                    "technical_passed": bool(record.get("technical_passed")),
                    "document_event_count": int(
                        metrics.get("document_event_count") or 0
                    ),
                    "personal": int(metrics.get("personal_event_count") or 0),
                    "context": int(metrics.get("context_event_count") or 0),
                    "uncertain": int(metrics.get("uncertain_event_count") or 0),
                    "needs_review": int(metrics.get("needs_review_count") or 0),
                }
            )

        expected = expected_windows.get(technical_id, 0)
        per_document.append(
            {
                "technical_document_id": technical_id,
                "document_id": document["document_id"],
                "interviewee": document["interviewee"],
                "source_format": document.get("source_format", ""),
                "expected_windows": expected,
                "passed_windows": passed_windows,
                "window_candidates": candidate_count,
                "edge_candidates": edge_count,
                "coverage_ok": coverage_ok,
                "raw_response_files": len(raw_files),
                "cross_window_pairs": queue_pairs,
                "terminal_candidate_ids": terminal_ids,
                **document_result,
            }
        )

    total_expected = sum(item["expected_windows"] for item in per_document)
    total_passed = sum(item["passed_windows"] for item in per_document)
    all_windows_present = all(
        item["passed_windows"] == item["expected_windows"]
        for item in per_document
    )
    all_document_results = all(
        item["exists"] and item["technical_passed"] for item in per_document
    )
    all_coverage = all(item["coverage_ok"] for item in per_document)
    all_raw_saved = all(item["raw_response_files"] > 0 for item in per_document)
    all_queues_saved = all(
        (queue_root / f"{item['technical_document_id']}.json").exists()
        for item in per_document
    )
    schema_pass_rate = (
        total_passed / total_expected if total_expected else 0.0
    )

    checks = {
        "json_and_schema_all_windows_passed": all_windows_present
        and not validation_error_details,
        "schema_pass_rate_at_least_95pct": schema_pass_rate >= 0.95,
        "segment_coverage_100pct": all_coverage,
        "edge_candidates_queued": all_queues_saved,
        "raw_responses_and_usage_saved": all_raw_saved,
        "document_consolidation_all_passed": all_document_results,
    }
    technical_gate = all(checks.values())
    price_in, price_out = prices_for(model)
    estimated_cost = (
        token_input * price_in + token_output * price_out
    ) / 1_000_000

    return {
        "summary_version": "v1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "batch_id": batch,
        "model_id": model,
        "run_track": run_track_for(model),
        "document_count": len(per_document),
        "expected_window_count": total_expected,
        "passed_window_count": total_passed,
        "schema_pass_rate": round(schema_pass_rate, 4),
        "token_input": token_input,
        "token_output": token_output,
        "estimated_cost_cny": round(estimated_cost, 4),
        "price_basis": (
            f"{model}：¥{price_in:g}/百万输入、¥{price_out:g}/百万输出"
        ),
        "checks": checks,
        "technical_gate_passed": technical_gate,
        "content_gate": "MANUAL_REVIEW_REQUIRED",
        "content_gate_note": (
            "集体战斗、历史背景是否被成批误纳为个人经历，"
            "必须人工抽检后才能进入下一批；本程序不自动放行。"
        ),
        "validation_error_details": validation_error_details,
        "per_document": per_document,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# {summary['batch_id']} / {summary['model_id']} 技术汇总",
        "",
        f"> 生成时间：{summary['generated_at']}；运行线：{summary['run_track']}（模型：{summary['model_id']}，结果按模型隔离）。",
        "",
        "## 技术门槛",
        "",
        "| 检查项 | 结果 |",
        "|---|---|",
    ]
    labels = {
        "json_and_schema_all_windows_passed": "全部窗口 JSON / Schema 通过",
        "schema_pass_rate_at_least_95pct": "Schema 通过率 ≥ 95%",
        "segment_coverage_100pct": "输入片段覆盖率 100%",
        "edge_candidates_queued": "窗口边缘候选已入复核队列",
        "raw_responses_and_usage_saved": "原始响应与 Token 已保存",
        "document_consolidation_all_passed": "文档级归并全部通过",
    }
    for key, label in labels.items():
        lines.append(f"| {label} | {'通过' if summary['checks'][key] else '未通过'} |")
    lines += [
        "| 集体背景误纳等内容熔断 | 需人工抽检 |",
        "",
        f"**技术结论：{'通过' if summary['technical_gate_passed'] else '未通过'}。** "
        "技术通过不等于本批可以自动进入下一批，仍须完成内容抽检。",
        "",
        "## 规模与成本",
        "",
        f"- 文档：{summary['document_count']}份",
        f"- 窗口：{summary['passed_window_count']}/{summary['expected_window_count']}通过",
        f"- 输入Token：{summary['token_input']:,}；输出Token：{summary['token_output']:,}",
        f"- 估算费用：¥{summary['estimated_cost_cny']:.4f}"
        f"（{summary.get('price_basis', '单价未标注')}，仅供登记参考）",
        "",
        "## 逐文档",
        "",
        "| 技术编号 | 受访者 | 窗口 | 窗口候选 | 文档事件 | 个人 | 背景 | 不确定 | 待复核 | 原始响应 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["per_document"]:
        lines.append(
            f"| `{item['technical_document_id']}` | {item['interviewee']} | "
            f"{item['passed_windows']}/{item['expected_windows']} | "
            f"{item['window_candidates']} | {item['document_event_count']} | "
            f"{item['personal']} | {item['context']} | {item['uncertain']} | "
            f"{item['needs_review']} | {item['raw_response_files']} |"
        )
    if summary["validation_error_details"]:
        lines += ["", "## 校验错误", ""]
        lines += [f"- {item}" for item in summary["validation_error_details"]]
    lines += [
        "",
        "## 下一步",
        "",
        "1. 人工抽检 `document_consolidation/validated_json/<模型目录>/` 中的范围分类与逐字证据；",
        "2. 确认没有集体战斗／历史背景成批进入个人事件链；",
        "3. 在实验登记表登记本批 Token 与费用；",
        "4. 再运行下一批：把 `--batch` 改为下一批次号。",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按批次运行 DeepSeek 全链路并生成熔断汇总"
    )
    parser.add_argument("--batch", required=True, help="批次号，如BATCH02")
    parser.add_argument("--model", default="cuc/deepseek")
    parser.add_argument(
        "--only-document",
        help="只运行一份文档，用于端到端验证，如BATCH02-DOC01",
    )
    parser.add_argument(
        "--skip-window",
        action="store_true",
        help="窗口已全部通过时跳过窗口阶段，只重建文档级输入并归并",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将执行的命令，不调用API、不写文件",
    )
    parser.add_argument(
        "--window-timeout", type=int, default=None,
        help="窗口级超时秒数；默认 DeepSeek 600、Qwen 1800",
    )
    parser.add_argument(
        "--document-timeout", type=int, default=None,
        help="文档级超时秒数；默认 DeepSeek 900、Qwen 2400",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重跑已有技术通过结果（旧原始响应不会删除）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    default_window_timeout, default_document_timeout = timeouts_for(args.model)
    if args.window_timeout is None:
        args.window_timeout = default_window_timeout
    if args.document_timeout is None:
        args.document_timeout = default_document_timeout
    batch = args.batch.upper()
    if not re.fullmatch(r"BATCH\d{2}", batch):
        print("错误：--batch 格式应为 BATCH02 这样的批次号。", file=sys.stderr)
        return 2
    lower = batch.lower()
    manifest_path = BATCH_ROOT / f"{lower}_manifest.csv"
    documents_path = BATCH_ROOT / f"{lower}_documents.json"
    for path in (manifest_path, documents_path):
        if not path.exists():
            print(
                f"错误：找不到{path.name}，请先运行"
                "prepare_batch_from_inventory.py",
                file=sys.stderr,
            )
            return 2

    with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    expected_windows = dict(
        Counter(row["technical_document_id"] for row in manifest)
    )
    documents = read_json(documents_path)
    if args.only_document:
        documents = [
            row
            for row in documents
            if row["technical_document_id"] == args.only_document.upper()
        ]
        if not documents:
            print(
                f"错误：{args.only_document} 不在 {batch} 的文档记录中。",
                file=sys.stderr,
            )
            return 2
    if not documents:
        print("错误：没有可运行的文档。", file=sys.stderr)
        return 2

    force_flag = ["--force"] if args.force else []
    commands: list[tuple[str, list[str]]] = []
    if not args.skip_window:
        for document in documents:
            technical_id = document["technical_document_id"]
            commands.append(
                (
                    f"窗口抽取 {technical_id}",
                    [
                        PYTHON,
                        "scripts/run_formal_batch.py",
                        "--model",
                        args.model,
                        "--batch",
                        batch,
                        "--document",
                        technical_id,
                        "--timeout",
                        str(args.window_timeout),
                        *force_flag,
                    ],
                )
            )

    prepare_command = [
        PYTHON,
        "scripts/prepare_document_consolidation.py",
        "--model",
        args.model,
        "--batch",
        batch,
    ]
    if args.only_document:
        prepare_command += ["--document", args.only_document.upper()]
    else:
        prepare_command += ["--all"]
    commands.append(("准备文档级归并输入", prepare_command))

    for document in documents:
        technical_id = document["technical_document_id"]
        commands.append(
            (
                f"文档级归并 {technical_id}",
                [
                    PYTHON,
                    "scripts/run_document_consolidation.py",
                    "--model",
                    args.model,
                    "--document",
                    technical_id,
                    "--timeout",
                    str(args.document_timeout),
                    *force_flag,
                ],
            )
        )

    print(
        f"{batch} / {args.model}：{len(documents)}份文档、"
        f"{sum(expected_windows.get(row['technical_document_id'], 0) for row in documents)}个窗口、"
        f"{len(commands)}个步骤。"
    )
    if args.dry_run:
        print("dry-run：以下命令不会执行。")
        for label, command in commands:
            print(f"  [{label}] " + " ".join(command))
        return 0

    for label, command in commands:
        return_code = run_step(command, label)
        if return_code != 0:
            print(
                f"\n本批在「{label}」中断。已完成结果全部保留，"
                "不要进入下一批；排查后可用同一命令断点续跑。",
                file=sys.stderr,
            )
            return return_code if return_code > 0 else 1

    summary = summarize(batch, args.model, documents, expected_windows)
    if args.only_document:
        stem = (
            f"{lower}_{args.only_document.lower()}_validation_"
            f"{safe_model_name(args.model)}"
        )
    else:
        stem = f"{lower}_summary_{safe_model_name(args.model)}"
    write_json(BATCH_ROOT / f"{stem}.json", summary)
    (BATCH_ROOT / f"{stem}.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    print(
        f"\n汇总已写入 {stem}.json / {stem}.md；"
        f"技术门槛{'通过' if summary['technical_gate_passed'] else '未通过'}。"
    )
    print("内容熔断仍需人工抽检后才能进入下一批。")
    return 0 if summary["technical_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
