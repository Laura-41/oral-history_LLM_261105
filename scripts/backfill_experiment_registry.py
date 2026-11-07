#!/usr/bin/env python3
"""从原始响应半自动补登实验登记表（默认只预览，--write 才写入）。

设计约束（研究者 2026-11-06）：
  - 不改动登记表 18 列结构，只在末尾追加缺失行；
  - 只填写可由原始响应客观推出的技术字段；
  - result_status / notes 不代填人工抽检与范围裁决结论，明确标注待研究者确认；
  - 幂等：以 (model_id, run_date, total_tokens) 为指纹，重跑不会重复登记；
  - 不调用任何 API，不修改任何原始响应或标注结果。

用法：
  python3 scripts/backfill_experiment_registry.py            # 只预览
  python3 scripts/backfill_experiment_registry.py --write    # 追加写入
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "01_实验配置" / "实验登记表.csv"

SCAN_PATTERNS = [
    "04_54份正式语料批处理/raw_responses/*/*.json",
    "04_54份正式语料批处理/document_consolidation/raw_responses/*/*.json",
    "03_六份Demo对照实验/01_受控事件包/results/*/*.json",
    "03_六份Demo对照实验/02_连续窗口盲抽取/results/*/*.json",
    "03_六份Demo对照实验/理论提示词最小测试/*.json",
]

PRICE_PER_MILLION = {
    "cuc/deepseek": (1.0, 4.0),
    "cuc/qwen": (3.0, 18.0),
}
ACTUAL_MODEL = {
    "cuc/deepseek": "DeepSeek-V4.1-Flash-1017",
    "cuc/qwen": "Qwen3.8-27B",
}
MODEL_TAG = {"cuc/deepseek": "DS", "cuc/qwen": "QW"}


def fingerprint(model: str, date: str, total_tokens: int) -> tuple[str, str, int]:
    return (model, date, int(total_tokens))


def date_of(record: dict, path: str) -> str:
    matched = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(record.get("run_time", "")))
    if matched:
        return f"{matched.group(1)}-{matched.group(2)}-{matched.group(3)}"
    matched = re.search(r"(20\d{6})_", os.path.basename(path))
    if matched:
        stamp = matched.group(1)
        return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
    return ""


def model_of(record: dict, path: str) -> str:
    model = record.get("model_id")
    if model:
        return model
    return "cuc/qwen" if "cuc_qwen" in path else "cuc/deepseek"


def identity_of(record: dict, path: str) -> tuple[str, str, str]:
    """返回 (document_id, input_scope, run_id 前缀)。"""
    stage = record.get("run_stage", "")
    window = record.get("window_id")
    tech_doc = record.get("technical_document_id")
    packet = record.get("packet_id")
    if window:
        scope = f"{len(record.get('input_segment_ids', []))}个原文片段／窗口抽取"
        return window, scope, window
    if tech_doc and stage == "DOCUMENT_CONSOLIDATION_AND_SCOPE":
        scope = (
            f"{len(record.get('input_candidate_ids', []))}个窗口候选"
            "／文档级归并与范围分类"
        )
        return tech_doc, scope, f"{tech_doc}-CONSOL"
    if packet:
        return packet, f"{packet}受控事件重建", packet
    matched = re.search(r"(WINDOW-\d+)", os.path.basename(path))
    if matched:
        name = matched.group(1)
        scope = f"{name}连续窗口盲抽取"
        stamp = re.search(r"(\d{6})_", os.path.basename(path).split("_", 1)[-1])
        suffix = f"-{stamp.group(1)}" if stamp else ""
        return name, scope, f"{name}{suffix}"
    matched = re.search(r"cuc_(?:deepseek|qwen)_(.+)\.json$", os.path.basename(path))
    if matched:
        name = f"TEST-{matched.group(1)}"
        return name, "理论提示词／边界／回归测试", name
    return os.path.basename(path)[:-5], "原始响应补登", "MISC"


def schema_of(record: dict) -> str:
    explicit = record.get("schema_version")
    if explicit:
        return explicit
    if record.get("run_stage") == "DOCUMENT_CONSOLIDATION_AND_SCOPE":
        return "document-consolidation-v1.0"
    return "event_candidate_v1.0"


def collect() -> tuple[list[dict], list[str], int, int]:
    with SHEET.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        existing_rows = list(reader)
    assert len(fields) == 18, f"登记表列数异常：{len(fields)}"
    known = {
        fingerprint(r["model_id"], r["run_date"], r["total_tokens"])
        for r in existing_rows
        if r["total_tokens"]
    }

    candidates: list[tuple[str, dict, str]] = []
    no_usage: list[str] = []
    scanned = 0
    for pattern in SCAN_PATTERNS:
        for path in sorted(glob.glob(str(ROOT / pattern))):
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
            usage = record.get("usage") or {}
            if not usage.get("total_tokens"):
                no_usage.append(os.path.relpath(path, ROOT))
                continue
            scanned += 1
            model = model_of(record, path)
            date = date_of(record, path)
            key = fingerprint(model, date, usage["total_tokens"])
            if key not in known:
                candidates.append((path, record, date))
                known.add(key)

    # run_id 必须在「已有登记行 + 本次新增行」范围内唯一：
    # 同一窗口在不同日期失败后重跑，会各自产生一份原始响应，若编号每批从 001 重来就会撞号。
    existing_ids = {r["run_id"] for r in existing_rows}
    counters: Counter[str] = Counter()
    rows: list[dict] = []
    for path, record, date in candidates:
        model = model_of(record, path)
        usage = record["usage"]
        price_in, price_out = PRICE_PER_MILLION.get(model, (1.0, 4.0))
        cost = (
            usage["prompt_tokens"] * price_in
            + usage["completion_tokens"] * price_out
        ) / 1_000_000
        document_id, scope, prefix = identity_of(record, path)
        tag = MODEL_TAG.get(model, "XX")
        while True:
            counters[prefix] += 1
            run_id = f"{prefix}-{tag}-{counters[prefix]:03d}"
            if run_id not in existing_ids:
                break
        existing_ids.add(run_id)
        tech_passed = bool(record.get("technical_passed"))
        errors = record.get("validation_errors") or record.get("schema_errors") or []
        status = "PASSED_WITH_REVIEW_NOTE" if tech_passed else "TECHNICAL_FAILED"
        rows.append({
            "run_id": run_id,
            "run_date": date,
            "stage": record.get("run_stage", ""),
            "model_id": model,
            "actual_model": ACTUAL_MODEL.get(model, model),
            "prompt_version": record.get("prompt_version", ""),
            "schema_version": schema_of(record),
            "document_id": document_id,
            "input_scope": scope,
            "temperature": "0",
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "duration_seconds": "",
            "cost_cny": f"{cost:.6f}",
            "json_valid": "true" if record.get("json_valid") else "false",
            "result_status": status,
            "notes": (
                "[自动补登·仅技术层] 来源="
                + os.path.relpath(path, ROOT)
                + f"；technical_passed={str(tech_passed).lower()}"
                + f"；validation_errors={len(errors)}"
                + "；内容抽检与范围裁决结论未由程序填写，待研究者确认。"
            ),
        })
    assert all(list(r.keys()) == fields for r in rows), "补登行字段与表头不一致"
    return rows, no_usage, len(existing_rows), scanned


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="实际追加写入登记表")
    args = parser.parse_args()

    rows, no_usage, before, scanned = collect()
    print(f"扫描有 usage 的原始响应：{scanned} 个")
    print(f"登记表原有行数：{before}（18 列）")
    print(f"待补登：{len(rows)} 行")
    print(f"无 usage（失败请求，不登记）：{len(no_usage)} 个")
    for path in no_usage:
        print(f"  - {path}")
    if rows:
        print("\n按模型：", dict(Counter(r["model_id"] for r in rows)))
        print("按阶段：", dict(Counter(r["stage"] for r in rows)))
        print("费用合计：¥", round(sum(float(r["cost_cny"]) for r in rows), 6))
        print("\n前 8 行预览：")
        for row in rows[:8]:
            print(
                f"  {row['run_id']} | {row['document_id']} | "
                f"{row['total_tokens']}tok | ¥{row['cost_cny']} | {row['result_status']}"
            )

    if not args.write:
        print("\n[预览模式] 未写入任何内容；确认后加 --write 执行。")
        return 0
    if not rows:
        print("\n无待补登行，登记表已是最新。")
        return 0

    with SHEET.open("rb") as handle:
        raw = handle.read()
    terminator = "\r\n" if raw.count(b"\r\n") > raw.count(b"\n") - raw.count(b"\r\n") else "\n"
    with SHEET.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator=terminator)
        writer.writerows(rows)
    with SHEET.open(encoding="utf-8-sig", newline="") as handle:
        after = list(csv.DictReader(handle))
    print(f"\n已追加 {len(rows)} 行；当前总行数 {len(after)}；列数仍为 {len(after[0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
