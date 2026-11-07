#!/usr/bin/env bash
# 大批量语料运行入口 —— 由研究者在本地终端自行启动。
#
# 约定来源（研究者 2026-11-06 明确要求）：
#   大批量跑语料时，助手只给出可直接复制的执行命令，不代为在对话里长时间运行；
#   研究者在自己的终端启动，实时看进度，避免对话窗口被长时间任务和日志撑长。
#   详见 04_54份正式语料批处理/DeepSeek_51份分批运行SOP.md §4.2，
#   以及 .workbuddy/memory/MEMORY.md 的「运行方式约定」。
#
# 用法（在工程根目录或任意目录均可）：
#   bash scripts/run_batches_in_terminal.sh                    # 依次跑 BATCH02–BATCH07，每批结束暂停等人工确认
#   bash scripts/run_batches_in_terminal.sh BATCH02            # 只跑一批
#   bash scripts/run_batches_in_terminal.sh BATCH03 BATCH04    # 指定多批
#   MODEL=cuc/qwen bash scripts/run_batches_in_terminal.sh BATCH02   # 换模型（结果按模型隔离）
#   DRY_RUN=1 AUTO_CONTINUE=1 bash scripts/run_batches_in_terminal.sh BATCH02  # 零API演练命令链
#   AUTO_CONTINUE=1 bash scripts/run_batches_in_terminal.sh     # 不暂停连跑（不推荐，会跳过每批人工熔断）
#
# 中断与续跑：Ctrl+C 随时可停；已技术通过的结果全部保留，用同一条命令重跑即断点续跑。
# 每批失败立即停止，不自动进入下一批。

set -o pipefail
cd "$(dirname "$0")/.." || exit 2

MODEL="${MODEL:-cuc/deepseek}"
MODEL_DIR="${MODEL//\//_}"

BATCHES=("$@")
if [ ${#BATCHES[@]} -eq 0 ]; then
  BATCHES=(BATCH02 BATCH03 BATCH04 BATCH05 BATCH06 BATCH07)
fi

LOG_DIR="04_54份正式语料批处理/run_logs"
mkdir -p "$LOG_DIR"

# macOS：阻止系统空闲休眠，避免长批跑到一半睡眠断网；Linux 无此命令时自动跳过。
PY_PREFIX=()
if command -v caffeinate >/dev/null 2>&1; then
  PY_PREFIX=(caffeinate -i)
fi

EXTRA=()
if [ "${DRY_RUN:-0}" = "1" ]; then
  EXTRA=(--dry-run)
fi

LOG_TAG=""
if [ "${DRY_RUN:-0}" = "1" ]; then
  LOG_TAG="_dryrun"
fi

# 记录失败退出码：内部批次熔断时，仍要把非零码传给外层调用者，
# 否则「for ... do bash 本脚本 && break; done」式的自动重试循环会把失败误判为成功并提前退出。
FAILED_CODE=0

for batch in "${BATCHES[@]}"; do
  stamp="$(date +%Y%m%d_%H%M%S)"
  # 加 shell PID：两个终端（DeepSeek / Qwen）同一秒启动时也不会 tee 到同一个日志文件。
  log="$LOG_DIR/${batch}_${MODEL_DIR}_${stamp}_pid$$${LOG_TAG}.log"
  lower="$(echo "$batch" | tr 'A-Z' 'a-z')"

  echo ""
  echo "===== 开始 ${batch} / ${MODEL}  $(date '+%F %T') ====="
  echo "日志：${log}"
  echo "另开终端窗口可实时查看：tail -f '${log}'"
  echo ""

  if "${PY_PREFIX[@]}" python3 -u scripts/run_deepseek_batch.py \
      --model "$MODEL" --batch "$batch" "${EXTRA[@]}" 2>&1 | tee "$log"; then
    echo ""
    echo "===== ${batch} 完成  $(date '+%F %T') ====="
    if [ "${DRY_RUN:-0}" != "1" ]; then
      echo "技术汇总：04_54份正式语料批处理/${lower}_summary_${MODEL_DIR}.md"
    fi
    if [ "${AUTO_CONTINUE:-0}" = "1" ]; then
      echo "AUTO_CONTINUE=1：跳过人工抽检提示，继续下一批（风险自负）。"
      continue
    fi
    echo "请先人工抽检 experience_scope 与逐字证据，并登记本批 Token／费用；"
    echo "确认后按回车继续下一批，按 Ctrl+C 结束。"
    read -r _ || { echo "输入结束，停在 ${batch}。"; break; }
  else
    code=$?
    FAILED_CODE=$code
    echo ""
    echo "===== ${batch} 中断（退出码 ${code}）  $(date '+%F %T') ====="
    echo "已完成的结果全部保留，不要进入下一批；排查后用同一条命令断点续跑。"
    break
  fi
done

exit "$FAILED_CODE"
