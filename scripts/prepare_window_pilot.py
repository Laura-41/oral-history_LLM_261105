#!/usr/bin/env python3
"""生成两个小型连续窗口测试包，并隔离人工答案。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
SOURCE_ROOT = PROJECT_DIR.parent / "现行标注"
OUTPUT_ROOT = PROJECT_DIR / "03_六份Demo对照实验" / "02_连续窗口盲抽取"

WINDOWS: tuple[dict[str, Any], ...] = (
    {
        "window_id": "WINDOW-01",
        "source_dir": "02_陈锐霆090422",
        "start_order": 18,
        "end_order": 27,
        "answer_file": "answer_key_v0.2.json",
        "selection_note": (
            "边界规则v0.2/v0.3回归；S0022同时结束幼年劳动叙述并触发"
            "观看日舰经历，可作为重叠过渡片段。"
        ),
        "expected_events": [
            {
                "legacy_event_id": "CRT-E01",
                "legacy_event_name": "八岁起放牛并承担家务劳动",
                "expected_type": "MATERIAL",
                "evidence_segment_ids": [
                    "CRT-01-S0018",
                    "CRT-01-S0020",
                    "CRT-01-S0022",
                ],
            },
            {
                "legacy_event_id": "CRT-E02",
                "legacy_event_name": "听说并观看日舰、遭炮击逃脱并形成仇日情绪",
                "expected_type": "MATERIAL",
                "evidence_segment_ids": [
                    "CRT-01-S0022",
                    "CRT-01-S0024",
                    "CRT-01-S0026",
                ],
            },
        ],
        "expected_unassigned_segment_ids": [
            "CRT-01-S0019",
            "CRT-01-S0021",
            "CRT-01-S0023",
            "CRT-01-S0025",
            "CRT-01-S0027",
        ],
    },
    {
        "window_id": "WINDOW-02",
        "source_dir": "01_陈海峰一访",
        "start_order": 42,
        "end_order": 54,
        "answer_file": "answer_key_WINDOW-02.json",
        "selection_note": (
            "第二个泛化窗口；测试组织罢工离厂与随后失业、重新就业两个相邻"
            "经历，S0050为共享过渡片段。"
        ),
        "expected_events": [
            {
                "legacy_event_id": "CHF-V1-E04",
                "legacy_event_name": "组织荣华印书馆工人罢工并离厂",
                "expected_type": "MATERIAL",
                "evidence_segment_ids": [
                    "CHF-V1-01-S0042",
                    "CHF-V1-01-S0044",
                    "CHF-V1-01-S0046",
                    "CHF-V1-01-S0048",
                    "CHF-V1-01-S0050",
                ],
            },
            {
                "legacy_event_id": "CHF-V1-E05",
                "legacy_event_name": "罢工离厂后经历失业并重新就业",
                "expected_type": "MATERIAL",
                "evidence_segment_ids": [
                    "CHF-V1-01-S0050",
                    "CHF-V1-01-S0052",
                    "CHF-V1-01-S0054",
                ],
            },
        ],
        "expected_unassigned_segment_ids": [
            "CHF-V1-01-S0043",
            "CHF-V1-01-S0045",
            "CHF-V1-01-S0047",
            "CHF-V1-01-S0049",
            "CHF-V1-01-S0051",
            "CHF-V1-01-S0053",
        ],
    },
    {
        "window_id": "WINDOW-03",
        "source_dir": "06_杨永松100506_01",
        "start_order": 20,
        "end_order": 30,
        "answer_file": "answer_key_WINDOW-03.json",
        "selection_note": (
            "第三个便利抽样窗口；直接取另一份语料YYS-01的S0020至S0030，"
            "不按预期事件数量优化。"
        ),
        "expected_events": [
            {
                "legacy_event_id": "YYS-E02",
                "legacy_event_name": "红军第一军团改编为八路军第一一五师",
                "expected_type": "MATERIAL",
                "evidence_segment_ids": [
                    "YYS-01-S0020",
                    "YYS-01-S0022",
                    "YYS-01-S0024",
                ],
                "window_coverage": "FULL",
            },
            {
                "legacy_event_id": "YYS-E03",
                "legacy_event_name": "红军战士接受换装并誓师开赴抗日前线",
                "expected_type": "MATERIAL",
                "evidence_segment_ids": [
                    "YYS-01-S0024",
                    "YYS-01-S0026",
                    "YYS-01-S0028",
                    "YYS-01-S0030",
                ],
                "window_coverage": "FULL",
            },
            {
                "legacy_event_id": "YYS-E04",
                "legacy_event_name": "第六八五团由三原行军渡黄河抵达侯马",
                "expected_type": "MATERIAL",
                "evidence_segment_ids": ["YYS-01-S0030"],
                "window_coverage": "PARTIAL_START_ONLY",
            },
        ],
        "expected_unassigned_segment_ids": [
            "YYS-01-S0021",
            "YYS-01-S0023",
            "YYS-01-S0025",
            "YYS-01-S0027",
            "YYS-01-S0029",
        ],
    },
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    manifest_rows: list[dict[str, Any]] = []
    for config in WINDOWS:
        source_dir = SOURCE_ROOT / config["source_dir"]
        documents = read_csv(source_dir / "documents.csv")
        segments = read_csv(source_dir / "source_segments.csv")
        start_order = config["start_order"]
        end_order = config["end_order"]
        selected = [
            row
            for row in segments
            if start_order <= int(row["segment_order"]) <= end_order
        ]
        expected_orders = list(range(start_order, end_order + 1))
        actual_orders = [int(row["segment_order"]) for row in selected]
        if actual_orders != expected_orders:
            raise RuntimeError(
                f"{config['window_id']}不连续：预期{expected_orders}，实际{actual_orders}"
            )

        document = documents[0]
        input_record = {
            "window_version": "v0.2",
            "window_id": config["window_id"],
            "doc_id": document["doc_id"],
            "document_title": document["title"],
            "interviewee": document["interviewee"],
            "task_scope": "连续窗口盲抽取；事件数量和边界未知，由模型自主判断。",
            "source_segments": [
                {
                    "segment_id": row["segment_id"],
                    "segment_order": int(row["segment_order"]),
                    "speaker_type": row["speaker_type"],
                    "segment_type": row["segment_type"],
                    "verbatim_text": row["verbatim_text"],
                }
                for row in selected
            ],
        }
        input_path = OUTPUT_ROOT / "inputs" / f"{config['window_id']}.json"
        write_json(input_path, input_record)

        answer_record = {
            "answer_key_version": "v0.3-boundary-evaluation",
            "warning": "仅用于模型完成后的边界评价，运行脚本不得读取本文件。",
            "window_id": config["window_id"],
            "selection_note": config["selection_note"],
            "expected_events": config["expected_events"],
            "expected_unassigned_segment_ids": config[
                "expected_unassigned_segment_ids"
            ],
        }
        answer_path = OUTPUT_ROOT / "answer_key" / config["answer_file"]
        write_json(answer_path, answer_record)

        manifest_rows.append(
            {
                "window_id": config["window_id"],
                "doc_id": document["doc_id"],
                "start_segment_order": start_order,
                "end_segment_order": end_order,
                "segment_count": len(selected),
                "source_characters": sum(
                    len(row["verbatim_text"]) for row in selected
                ),
                "input_file": f"inputs/{config['window_id']}.json",
                "answer_file": f"answer_key/{config['answer_file']}",
            }
        )

    manifest_path = OUTPUT_ROOT / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"已生成{len(manifest_rows)}个连续窗口测试包：{OUTPUT_ROOT}")
    for row in manifest_rows:
        print(
            f"  {row['window_id']}：{row['segment_count']}个连续片段，"
            f"{row['source_characters']}字"
        )
    print("人工答案已隔离保存。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
