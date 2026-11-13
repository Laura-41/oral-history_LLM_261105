#!/usr/bin/env bash
# 图谱补齐：单份文档端到端验证（L0 → L1/L2 → 后处理 → 18 表校验 → 24 表导出）
# 由研究者在本地终端启动；长任务不代跑。失败即停，已完成结果全部保留，重跑同一命令即断点续跑。
#
# 用法：
#   bash scripts/graph_verify_one_document.sh
#   bash scripts/graph_verify_one_document.sh BATCH02-DOC01 cuc/qwen
#   MODEL=cuc/deepseek bash scripts/graph_verify_one_document.sh BATCH02-DOC01
#   TIMEOUT=3600 MODEL=cuc/deepseek bash scripts/graph_verify_one_document.sh BATCH02-DOC01
#     ↑ 上次 DeepSeek 的 entity_time 等满 1800 秒超时；可显式加大单次等待上限（断点续跑不变）

set -euo pipefail

DOC="${1:-BATCH02-DOC01}"
MODEL="${2:-${MODEL:-cuc/qwen}}"
MODEL_DIR="${MODEL//\//_}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date +%Y%m%d_%H%M%S)_pid$$"
LOG_DIR="04_54份正式语料批处理/run_logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/GRAPH_VERIFY_${DOC}_${MODEL_DIR}_${STAMP}.log"

echo "单文档验证：$DOC / $MODEL" | tee "$LOG"
echo "日志：$LOG" | tee -a "$LOG"
echo "长任务由本地终端执行；Ctrl+C 可停，重跑同一命令即断点续跑。" | tee -a "$LOG"

run() {
  local label="$1"; shift
  echo "" | tee -a "$LOG"
  echo "===== $label =====" | tee -a "$LOG"
  if ! "$@" 2>&1 | tee -a "$LOG"; then
    echo "" | tee -a "$LOG"
    echo "熔断于：${label}。已完成结果全部保留，修好后重跑同一命令即可。" | tee -a "$LOG"
    exit 1
  fi
}

run "L0 零 API 底座表" python3 -u scripts/graph_build_base_tables.py --document "$DOC" --model "$MODEL" --write
run "L1/L2 模型任务（真实 API 调用）" python3 -u scripts/graph_run_enrichment.py --document "$DOC" --model "$MODEL" --task all --write --timeout "${TIMEOUT:-1800}"
run "后处理：校验、算偏移、生成 18 张 CSV" python3 -u scripts/graph_apply_enrichment.py --document "$DOC" --model "$MODEL" --write
run "18 表完整性验收" python3 -u scripts/graph_validate_bundle.py --document "$DOC" --model "$MODEL" --write-report
run "L3/L4 导出 24 张 import CSV" python3 -u scripts/graph_export_import.py --model "$MODEL" --write

echo "" | tee -a "$LOG"
echo "===== 完成 =====" | tee -a "$LOG"
echo "结果：04_54份正式语料批处理/document_consolidation/graph_layers/$MODEL_DIR/$DOC/" | tee -a "$LOG"
echo "图谱导入：05_合并与Neo4j/import_$MODEL_DIR/" | tee -a "$LOG"
echo "请把 VALIDATION_report.json 与 prepare_summary.json 交助手复核，再决定是否放行 BATCH03。" | tee -a "$LOG"
