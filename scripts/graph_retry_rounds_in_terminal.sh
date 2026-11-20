#!/usr/bin/env bash
# 图谱新增层「有限轮次」外层编排：跑完一轮再跑一轮，直到 54 份全部 valid=true。
#
# 只反复调用既有 graph_run_all_in_terminal.sh，不改其一字；
# 不改提示词 / Schema / 校验规则 / 数据 / 原始结果。每轮天然断点续跑，已验收文档自动跳过。
#
# 用法（先 cd 到工程根）：
#   caffeinate -i env MODEL=cuc/qwen TIMEOUT=3600 SKIP_AFTER=2 ROUNDS=3 \
#     bash scripts/graph_retry_rounds_in_terminal.sh
#   WAIT_FOR_CURRENT=0 ...   # 当前终端已空闲：跳过等待，立即开跑
#   DRY_RUN=1 WAIT_FOR_CURRENT=0 ...   # 零 API 演练，只打印当前完成度与轮次计划
#
# 参数（全部有默认值；TIMEOUT / SKIP_AFTER 沿用研究者裁决值，勿改）：
#   MODEL            默认 cuc/qwen
#   TIMEOUT          默认 3600   Qwen 线单次 API 等待上限
#   SKIP_AFTER       默认 2      单份最多试 2 次，仍失败先跳过跑后面的；本轮未全量则不统一导出、禁止入库
#   ROUNDS           默认 3      有限轮次（实测第 3 轮以上无收益），禁止无限 while
#   SLEEP_BETWEEN    默认 180    轮间等待，避开上游拥堵
#   TARGET           默认 54     达标份数
#   WAIT_FOR_CURRENT 默认 1     先等当前在跑的图谱任务退出，避免同模型两条命令并行
#   MAX_WAIT         默认 14400  最多等 4 小时；超时主动退出而不是盲目并行
#   DRY_RUN          默认 0      1 = 零 API 演练
#
# 达标判据：graph_layers/<模型>/<文档>/VALIDATION_report.json 中 valid=true 的份数 == TARGET。
# 3 轮跑完仍未齐属正常（上游拥堵），会列出剩余清单；重跑同一条命令即继续补，已成功结果全部保留。

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODEL="${MODEL:-cuc/qwen}"
MODEL_DIR="${MODEL//\//_}"
TIMEOUT="${TIMEOUT:-3600}"
SKIP_AFTER="${SKIP_AFTER:-2}"
ROUNDS="${ROUNDS:-3}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-180}"
TARGET="${TARGET:-54}"
WAIT_FOR_CURRENT="${WAIT_FOR_CURRENT:-1}"
MAX_WAIT="${MAX_WAIT:-14400}"
DRY_RUN="${DRY_RUN:-0}"

LAYER="04_54份正式语料批处理/document_consolidation"
OUT="$LAYER/graph_layers/$MODEL_DIR"
SRC="$LAYER/validated_json/$MODEL_DIR"
LOG_DIR="04_54份正式语料批处理/run_logs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)_pid$$"
LOG="$LOG_DIR/GRAPH_ROUNDS_${MODEL_DIR}_${STAMP}.log"

count_valid() {
  python3 - "$OUT" <<'PY'
import glob, json, os, sys
n = 0
for p in glob.glob(os.path.join(sys.argv[1], '*', 'VALIDATION_report.json')):
    try:
        with open(p, encoding='utf-8') as f:
            if json.load(f).get('valid') is True:
                n += 1
    except Exception:
        pass
print(n)
PY
}

list_missing() {
  python3 - "$SRC" "$OUT" <<'PY'
import glob, json, os, sys
src, out = sys.argv[1], sys.argv[2]
ok = set()
for p in glob.glob(os.path.join(out, '*', 'VALIDATION_report.json')):
    try:
        with open(p, encoding='utf-8') as f:
            if json.load(f).get('valid') is True:
                ok.add(os.path.basename(os.path.dirname(p)))
    except Exception:
        pass
docs = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(src, '*.json')))
missing = [d for d in docs if d not in ok]
print(' '.join(missing) if missing else '(无)')
PY
}

graph_busy() {
  pgrep -f 'scripts/graph_run_enrichment\.py' >/dev/null 2>&1 && return 0
  pgrep -f 'scripts/graph_verify_one_document\.sh' >/dev/null 2>&1 && return 0
  pgrep -f 'scripts/graph_run_all_in_terminal\.sh' >/dev/null 2>&1 && return 0
  return 1
}

log() { echo "$*" | tee -a "$LOG"; }

log "===== 图谱新增层轮次编排 | ${MODEL} | $(date '+%F %T') ====="
log "配置：TIMEOUT=${TIMEOUT}s  SKIP_AFTER=${SKIP_AFTER}  ROUNDS=${ROUNDS}  轮间=${SLEEP_BETWEEN}s  目标=${TARGET} 份"
log "总日志：${LOG}（原脚本每轮另写带模型/时间/PID 的独立日志）"
log "口径：Qwen 线为进度冗余备份；正式结果仍只用 DeepSeek 单线，本命令产物不入库。"
log "当前完成度：$(count_valid)/${TARGET}"
if [ "$DRY_RUN" = "1" ]; then
  log "[演练] 不调用任何 API。剩余：$(list_missing)"
  exit 0
fi
log ""

if [ "$WAIT_FOR_CURRENT" = "1" ]; then
  waited=0
  while graph_busy; do
    if [ "$waited" -ge "$MAX_WAIT" ]; then
      log "⚠️ 已等待 ${waited}s，当前图谱任务仍未结束。为避免同模型两条命令并行，本命令主动退出；请确认后重跑。"
      exit 2
    fi
    if [ $((waited % 300)) -eq 0 ]; then
      log "[等待] 检测到仍有图谱任务在跑，已等 ${waited}s  $(date '+%H:%M:%S')（不会并行调用）"
    fi
    sleep 30
    waited=$((waited + 30))
  done
  log "[等待] 当前图谱任务已结束，开始轮次编排。"
  log ""
fi

for round in $(seq 1 "$ROUNDS"); do
  before=$(count_valid)
  if [ "$before" -ge "$TARGET" ]; then
    log "已达标 ${before}/${TARGET}，无需再跑。"
    break
  fi
  log "===== 第 ${round}/${ROUNDS} 轮开始 | 当前 ${before}/${TARGET} | $(date '+%F %T') ====="
  MODEL="$MODEL" TIMEOUT="$TIMEOUT" SKIP_AFTER="$SKIP_AFTER" \
    bash scripts/graph_run_all_in_terminal.sh 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  log "第 ${round} 轮脚本退出码：${rc}（非 0 也会在下一轮断点续跑，已成功结果全部保留）"
  after=$(count_valid)
  log "===== 第 ${round}/${ROUNDS} 轮结束 | ${before} → ${after}/${TARGET} | 本轮补回 $((after - before)) 份 ====="
  if [ "$after" -ge "$TARGET" ]; then
    log "✅ 全部 ${TARGET} 份已 valid=true，停止轮次。"
    break
  fi
  if [ "$round" -lt "$ROUNDS" ]; then
    log "轮间等待 ${SLEEP_BETWEEN}s ..."
    sleep "$SLEEP_BETWEEN"
  fi
  log ""
done

final=$(count_valid)
log ""
if [ "$final" -ge "$TARGET" ]; then
  log "===== 结果：${final}/${TARGET} 全部通过 18 表验收 ====="
  log "原脚本在最后全量时会自动统一重导 24 表到 05_合并与Neo4j/import_${MODEL_DIR}/。"
  log "⚠️ 该目录属 Qwen 备份产物：不要导入 Neo4j，不要与 DeepSeek 正式包混用；正式线仍是 oral-history-all60-v1。"
else
  log "===== 结果：${final}/${TARGET}，有限 ${ROUNDS} 轮已用完，仍差 $((TARGET - final)) 份 ====="
  log "剩余文档：$(list_missing)"
  log "待补跑清单亦见 04_54份正式语料批处理/review_queue/graph_pending_${MODEL_DIR}.md（若本轮有跳过）。"
  log "第 3 轮以上实测无收益，不要改写成无限 while；等上游恢复后【重跑同一条命令】即继续补，已成功结果全保留。"
  log "⚠️ 未全量时不导出、不入库。"
fi
log "总日志：$LOG"
exit 0
