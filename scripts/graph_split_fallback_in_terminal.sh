#!/usr/bin/env bash
# entity_time 分段兜底（旁路入口，仅用于反复超时的顽固文档）
#
# 由研究者在本地终端启动；助手不代跑。失败即停，已完成的分段全部保留，
# 重跑同一命令即断点续跑。本脚本不修改任何既有脚本／提示词／Schema／校验器。
#
# 用法：
#   bash scripts/graph_split_fallback_in_terminal.sh
#   DOCS="BATCH02-DOC09 BATCH04-DOC09" PARTS=2 bash scripts/graph_split_fallback_in_terminal.sh
#   MODEL=cuc/qwen DOCS="BATCH07-DOC06" PARTS=3 bash scripts/graph_split_fallback_in_terminal.sh
#
# 前置：若同一模型线的 graph_run_all_in_terminal.sh 仍在跑，先 Ctrl+C 停掉，
#       避免两个进程写同一份文档的 raw 目录。另一条模型线不用动。

set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:-cuc/deepseek}"
MODEL_DIR="${MODEL//\//_}"
PARTS="${PARTS:-2}"
TIMEOUT="${TIMEOUT:-1800}"
DOCS="${DOCS:-BATCH02-DOC09 BATCH04-DOC09}"
LAYER_ROOT="04_54份正式语料批处理/document_consolidation"
OUT="$LAYER_ROOT/graph_layers/$MODEL_DIR"
LOG_DIR="04_54份正式语料批处理/run_logs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)_pid$$"
LOG="$LOG_DIR/GRAPH_SPLIT_${MODEL_DIR}_${STAMP}.log"

run() {
  local label="$1"; shift
  echo "" | tee -a "$LOG"
  echo "===== $label =====" | tee -a "$LOG"
  if ! "$@" 2>&1 | tee -a "$LOG"; then
    echo "" | tee -a "$LOG"
    echo "熔断于：${label}。已完成的分段全部保留，重跑同一命令即断点续跑。" | tee -a "$LOG"
    echo "若某一段反复失败，用 PARTS=3 再跑一次（切成 3 段，每段更小）。" | tee -a "$LOG"
    exit 1
  fi
}

main() {
  echo "entity_time 分段兜底：$MODEL ｜切 $PARTS 段｜单次等待上限 ${TIMEOUT}s" | tee "$LOG"
  echo "日志：$LOG" | tee -a "$LOG"
  echo "长任务由本地终端执行；Ctrl+C 可停，重跑同一命令即断点续跑。" | tee -a "$LOG"
  echo "文档：$DOCS" | tee -a "$LOG"
  echo "" | tee -a "$LOG"
  echo "口径提醒：分段结果与其余 52 份不完全同口径，仍为 MODEL_CANDIDATE；" | tee -a "$LOG"
  echo "          论文方法章须注明，人工抽检重点看实体去重与事件时间。" | tee -a "$LOG"

  local d
  for d in $DOCS; do
    echo "" | tee -a "$LOG"
    echo "########## $d ##########" | tee -a "$LOG"

    if [ -f "$OUT/$d/VALIDATION_report.json" ] && python3 -c \
      'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("valid") else 1)' \
      "$OUT/$d/VALIDATION_report.json" 2>/dev/null; then
      echo "$d 已完整验收，跳过。" | tee -a "$LOG"
      continue
    fi

    run "$d 分段调用 + 确定性合并（真实 API）" \
      caffeinate -i python3 -u scripts/graph_entity_time_split_fallback.py \
        --document "$d" --model "$MODEL" --parts "$PARTS" --timeout "$TIMEOUT" --write

    run "$d 后处理：校验、算偏移、生成 18 张 CSV（零 API）" \
      python3 -u scripts/graph_apply_enrichment.py --document "$d" --model "$MODEL" --write

    run "$d 18 表完整性验收（零 API）" \
      python3 -u scripts/graph_validate_bundle.py --document "$d" --model "$MODEL" --write-report
  done

  echo "" | tee -a "$LOG"
  echo "===== 分段兜底全部完成 =====" | tee -a "$LOG"
  python3 -c '
import glob,json,sys
lay="04_54份正式语料批处理/document_consolidation/graph_layers/"+sys.argv[1]
v=sum(1 for f in glob.glob(lay+"/*/VALIDATION_report.json") if json.load(open(f)).get("valid"))
print(f"当前 {sys.argv[1]} 完整验收 {v}/54")
' "$MODEL_DIR" | tee -a "$LOG"
  echo "" | tee -a "$LOG"
  echo "下一步：重跑主链，让它识别这两份并统一导出 24 表（已验收的会自动跳过，零 API）：" | tee -a "$LOG"
  echo "  caffeinate -i env TIMEOUT=${TIMEOUT} MODEL=${MODEL} SKIP_AFTER=2 bash scripts/graph_run_all_in_terminal.sh" | tee -a "$LOG"
  echo "" | tee -a "$LOG"
  echo "统一导出完成后才可导入 Neo4j；结果一律 MODEL_CANDIDATE，人工放行仍由研究者完成。" | tee -a "$LOG"
}

main "$@" 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
