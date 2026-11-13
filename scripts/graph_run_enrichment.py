#!/usr/bin/env python3
"""图谱补齐 L1/L2：运行新增的两个模型任务，只保存原始响应，不写最终 CSV。

输出到 document_consolidation/graph_layers/<模型目录>/<文档>/raw/。
后处理（校验、算偏移、生成 CSV）由 graph_apply_enrichment.py 完成，
因此可以随时用同一份原始响应重跑后处理，无需重新调用 API。

用法（长任务请由研究者在本地终端启动）：
    python3 scripts/graph_run_enrichment.py --document BATCH02-DOC01 --task all          # 预演，零 API
    python3 scripts/graph_run_enrichment.py --document BATCH02-DOC01 --task all --write   # 真实调用
    python3 scripts/graph_run_enrichment.py --document BATCH02-DOC01 --task stage --model cuc/qwen --write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from api_test import extract_content, get_api_key, request_json  # noqa: E402
from graph_build_base_tables import (  # noqa: E402
    GRAPH_ROOT,
    display_path,
    load_context,
    safe_model_name,
)

CONTRACT_DIR = PROJECT_DIR / "02_Schema与提示词" / "graph_enrichment_v1.0"
PROMPT_FILES = {
    "stage": CONTRACT_DIR / "prompt_stage_v1.0.txt",
    "entity_time": CONTRACT_DIR / "prompt_entity_time_v1.0.txt",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def strip_json_fence(content: str) -> str:
    content = content.strip()
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def segment_text_map(ctx: dict[str, Any]) -> dict[str, str]:
    return {row["segment_id"]: row.get("verbatim_text", "") for row in ctx["segments"]}


def build_stage_packets(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    texts = segment_text_map(ctx)
    packets = []
    for event in ctx["events"]:
        canonical = event["canonical_event"]
        ids = event.get("source_segment_ids", [])
        packets.append({
            "document_id": ctx["doc_meta"]["doc_id"],
            "event_id": event["document_event_id"],
            "event": {
                "event_name": canonical.get("event_name", ""),
                "event_type": canonical.get("event_type", ""),
                "core_process": canonical.get("core_process", ""),
                "participants": canonical.get("participants", []),
                "circumstances": canonical.get("circumstances", []),
                "evidence_quote": canonical.get("evidence_quote", ""),
                "source_segment_ids": ids,
            },
            "source_segments": [
                {"segment_id": sid, "verbatim_text": texts.get(sid, "")}
                for sid in ids if sid in texts
            ],
        })
    return packets


def build_entity_time_packet(ctx: dict[str, Any]) -> dict[str, Any]:
    meta = ctx["doc_meta"]
    events = []
    for event in ctx["events"]:
        canonical = event["canonical_event"]
        times = [
            c for c in canonical.get("circumstances", []) if c.get("kind") == "TIME"
        ]
        events.append({
            "event_id": event["document_event_id"],
            "event_name": canonical.get("event_name", ""),
            "time_circumstances": times,
            "source_segment_ids": event.get("source_segment_ids", []),
        })
    return {
        "document_id": meta["doc_id"],
        "interviewee": meta["interviewee"],
        "source_segments": [
            {
                "segment_id": row["segment_id"],
                "segment_type": row.get("segment_type", ""),
                "part": row.get("part", ""),
                "speaker_type": row.get("speaker_type", ""),
                "verbatim_text": row.get("verbatim_text", ""),
            }
            for row in sorted(ctx["segments"], key=lambda r: int(r["segment_order"]))
        ],
        "events": events,
    }


def raw_dir(ctx: dict[str, Any]) -> Path:
    return GRAPH_ROOT / ctx["model_dir"] / ctx["technical_id"] / "raw"


def already_done(folder: Path, prefix: str) -> bool:
    for path in folder.glob(f"{prefix}_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("parsed") is not None and not data.get("request_error"):
                return True
        except (json.JSONDecodeError, OSError):
            continue
    return False


def run_one(
    *,
    task: str,
    key: str,
    packet: dict[str, Any],
    system_prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout: int,
    folder: Path,
    dry_run: bool,
    index: int,
    total: int,
) -> bool:
    prefix = f"{task}_{key}"
    if already_done(folder, prefix):
        print(f"  [{index}/{total}] {prefix} 已有成功响应，跳过（断点续跑）")
        return True

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
        ],
        "temperature": 0,
        "stream": False,
    }
    size = len(json.dumps(payload, ensure_ascii=False))
    if dry_run:
        print(f"  [{index}/{total}] {prefix} 预演：输入包 {size:,} 字符，未调用 API")
        return True

    print(f"  [{index}/{total}] 请求 {task}/{key}，输入 {size:,} 字符，最长等待 {timeout}s……", flush=True)
    started = datetime.now()
    response: dict[str, Any] | None = None
    raw_content = ""
    request_error: str | None = None
    try:
        response = request_json(
            method="POST",
            url=f"{base_url}/chat/completions",
            api_key=api_key,
            payload=payload,
            timeout=timeout,
        )
        raw_content = extract_content(response)
    except RuntimeError as exc:
        request_error = str(exc)

    timestamp = started.strftime("%Y%m%d_%H%M%S")
    record: dict[str, Any] = {
        "run_time": started.isoformat(timespec="seconds"),
        "run_stage": f"GRAPH_ENRICHMENT_{task.upper()}",
        "task": task,
        "packet_key": key,
        "model_id": model,
        "prompt_version": "graph_enrichment_v1.0",
        "schema_version": "v1.0",
        "technical_document_id": packet.get("event_id", key),
        "usage": (response or {}).get("usage", {}),
        "raw_content": raw_content,
        "parsed": None,
        "request_error": request_error,
    }
    if request_error:
        write_json(folder / f"{prefix}_{timestamp}_FAILED.json", record)
        print(f"  失败并停止：{request_error}", file=sys.stderr)
        return False

    try:
        record["parsed"] = json.loads(strip_json_fence(raw_content))
    except json.JSONDecodeError as exc:
        record["parse_error"] = str(exc)
        write_json(folder / f"{prefix}_{timestamp}_PARSEERROR.json", record)
        print(f"  JSON 解析失败并停止：{exc}", file=sys.stderr)
        return False

    write_json(folder / f"{prefix}_{timestamp}.json", record)
    usage = record["usage"] or {}
    print(f"  完成：total_tokens={usage.get('total_tokens', '?')}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", required=True, help="技术文档ID，如 BATCH02-DOC01")
    parser.add_argument("--model", default="cuc/qwen", help="新增层默认主模型")
    parser.add_argument("--task", choices=("stage", "entity_time", "all"), default="all")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--write", action="store_true", help="真实调用 API；默认只预演")
    args = parser.parse_args()

    try:
        ctx = load_context(args.document, args.model)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 2

    tasks = ("stage", "entity_time") if args.task == "all" else (args.task,)
    folder = raw_dir(ctx)
    api_key = ""
    base_url = ""
    if args.write:
        api_key = get_api_key()
        if not api_key:
            print("错误：环境变量和钥匙串均没有 API 密钥。", file=sys.stderr)
            return 2
        base_url = os.environ.get("CUC_BASE_URL", "https://openai.cuc.edu.cn/v1").rstrip("/")

    print(f"{'[真实调用]' if args.write else '[零 API 预演]'} {args.document} / {args.model} / tasks={','.join(tasks)}")
    print(f"  一级事件 {len(ctx['events'])}｜原文片段 {len(ctx['segments'])}｜输出目录 {display_path(folder)}")

    overall = 0
    for task in tasks:
        system_prompt = PROMPT_FILES[task].read_text(encoding="utf-8")
        if task == "stage":
            packets = [(p["event_id"], p) for p in build_stage_packets(ctx)]
        else:
            packets = [(ctx["doc_meta"]["doc_id"], build_entity_time_packet(ctx))]
        print(f"\n== {task}：{len(packets)} 次调用 ==")
        for index, (key, packet) in enumerate(packets, start=1):
            ok = run_one(
                task=task, key=key, packet=packet, system_prompt=system_prompt,
                model=args.model, api_key=api_key, base_url=base_url,
                timeout=args.timeout, folder=folder, dry_run=not args.write,
                index=index, total=len(packets),
            )
            if not ok:
                print(f"\n{task} 在第 {index} 次调用熔断；已完成结果全部保留，重跑同一命令即断点续跑。", file=sys.stderr)
                return 1
            overall += 1

    print(f"\n全部完成：{overall} 次调用。下一步：python3 scripts/graph_apply_enrichment.py --document {args.document} --model {args.model} --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
