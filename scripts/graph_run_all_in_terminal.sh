#!/usr/bin/env bash
# 图谱新增层批量执行入口（由研究者在本地终端启动，助手不代跑长任务）。
#
# 逐份跑：L0 底座表 → L1/L2 模型任务 → 后处理 → 18 表验收 → 24 表导出。
# 只枚举「一级层已有 validated_json 结果」的文档；已通过验收的自动跳过，天然断点续跑。
# 失败即停，已完成结果全部保留，重跑同一命令即继续。
#
# 用法（先 cd 到工程根）：
#   caffeinate -i bash scripts/graph_run_all_in_terminal.sh                       # Qwen 线
#   caffeinate -i env MODEL=cuc/deepseek bash scripts/graph_run_all_in_terminal.sh  # DeepSeek 线
#   DOCS="BATCH02-DOC02 BATCH02-DOC03" bash scripts/graph_run_all_in_terminal.sh   # 只跑指定文档
#   TIMEOUT=3600 bash scripts/graph_run_all_in_terminal.sh                       # Qwen 线：加大单次 API 等待上限
#   TIMEOUT=1200 bash scripts/graph_run_all_in_terminal.sh                       # DeepSeek 线：20 分钟提前放弃注定失败的大请求
#   DRY_RUN=1 bash scripts/graph_run_all_in_terminal.sh                          # 零 API 演练，只列清单
#   SKIP_AFTER=2 bash scripts/graph_run_all_in_terminal.sh                       # 每份最多试 2 次，仍失败先跳过跑后面的
#   STAGE_ONLY=1 bash scripts/graph_run_all_in_terminal.sh                       # 只跑快的 stage（不碰 entity_time/后处理/导出）
#
# SKIP_AFTER（默认 0 = 保持原「失败即停」口径）：仅改运行编排，不改提示词/Schema/校验规则/数据。
# 启用后，单份文档连续失败达上限即写入 review_queue/graph_pending_<模型>.md 并继续下一份；
# 本轮有跳过文档时【不执行统一导出 24 表】，并明确提示未全量、禁止入库。
#
# 两条模型线可同时各开一个终端：日志名含模型、时间戳与进程号，写入点按模型目录隔离。

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODEL="${MODEL:-cuc/qwen}"
MODEL_DIR="${MODEL//\//_}"
TIMEOUT="${TIMEOUT:-1800}"
DRY_RUN="${DRY_RUN:-0}"
SKIP_AFTER="${SKIP_AFTER:-0}"
STAGE_ONLY="${STAGE_ONLY:-0}"

LAYER_ROOT="04_54份正式语料批处理/document_consolidation"
SRC="$LAYER_ROOT/validated_json/$MODEL_DIR"
OUT="$LAYER_ROOT/graph_layers/$MODEL_DIR"
LOG_DIR="04_54份正式语料批处理/run_logs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)_pid$$"
LOG="$LOG_DIR/GRAPH_ALL_${MODEL_DIR}_${STAMP}.log"

is_done() {
  [ -f "$OUT/$1/VALIDATION_report.json" ] || return 1
  python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("valid") else 1)' \
    "$OUT/$1/VALIDATION_report.json" 2>/dev/null
}

main() {
  echo "图谱新增层批量执行：$MODEL"
  echo "日志：$LOG"
  echo "长任务由本地终端执行；Ctrl+C 可停，重跑同一命令即断点续跑。"
  echo "单次 API 等待上限：${TIMEOUT}s（DeepSeek 大请求上游固定 30 分钟回 500/504，建议 1200 提前放弃；Qwen 线用 3600）"
  if [ "$STAGE_ONLY" = "1" ]; then
    echo "运行模式：STAGE ONLY —— 只跑快的二级阶段；不调用 entity_time、不做后处理/验收/导出"
  elif [ "$SKIP_AFTER" -gt 0 ]; then
    echo "容错编排：每份最多尝试 ${SKIP_AFTER} 次，仍失败先跳过跑后面的（未全量则不导出、禁止入库）"
  else
    echo "容错编排：关闭（失败即停，重跑同一命令即断点续跑）"
  fi
  echo "语料口径：60 份总账 = 6 份人工 Demo + 54 份正式语料；BATCH01 三份同为正式语料，全数纳入。"
  echo ""

  if [ ! -d "$SRC" ]; then
    echo "找不到一级层结果目录：$SRC"
    return 1
  fi

  local -a docs=()
  if [ -n "${DOCS:-}" ]; then
    read -ra docs <<< "$DOCS"
  else
    local f
    for f in "$SRC"/*.json; do
      [ -e "$f" ] || continue
      local name
      name="$(basename "$f" .json)"
      docs+=("$name")
    done
  fi

  if [ "${#docs[@]}" -eq 0 ]; then
    echo "没有可跑的文档；请先完成一级层批次。"
    return 1
  fi

  local done_count=0 todo=0
  local d
  for d in "${docs[@]}"; do
    if is_done "$d"; then
      done_count=$((done_count + 1))
    else
      todo=$((todo + 1))
    fi
  done
  echo "一级层结果 ${#docs[@]} 份｜新增层已验收 $done_count 份｜本次待跑 $todo 份"
  echo "待跑清单："
  for d in "${docs[@]}"; do
    if ! is_done "$d"; then echo "  $d"; fi
  done
  echo ""

  if [ "$DRY_RUN" = "1" ]; then
    echo "[演练] 不调用任何 API，也不写任何结果。去掉 DRY_RUN=1 才会真跑。"
    return 0
  fi

  if [ "$STAGE_ONLY" = "1" ]; then
    local stage_ok=0 stage_fail=0 stage_index=0
    for d in "${docs[@]}"; do
      stage_index=$((stage_index + 1))
      if is_done "$d"; then
        echo "[${stage_index}/${#docs[@]}] ${d} 已完整验收，跳过"
        continue
      fi
      echo "[${stage_index}/${#docs[@]}] ===== ${d} 只跑 stage ====="
      if python3 -u scripts/graph_run_enrichment.py --document "$d" --model "$MODEL" --task stage --write --timeout "$TIMEOUT"; then
        stage_ok=$((stage_ok + 1))
      else
        stage_fail=$((stage_fail + 1))
        echo "⚠️ ${d} 的 stage 本轮未跑齐；重跑同一命令即断点续跑（已成功的自动跳过）。"
      fi
    done
    echo ""
    echo "===== stage 专跑结束：本轮跑齐 ${stage_ok} 份，未跑齐 ${stage_fail} 份 ====="
    echo "本模式不调用 entity_time、不做后处理／验收／导出；落盘的只是原始响应，仍需跑正常命令补全。"
    echo "下一步：caffeinate -i env TIMEOUT=1200 MODEL=${MODEL} SKIP_AFTER=2 bash scripts/graph_run_all_in_terminal.sh"
    return 0
  fi

  local index=0
  local skipped_count=0
  local skipped_list=""
  for d in "${docs[@]}"; do
    index=$((index + 1))
    if is_done "$d"; then
      echo "[$index/${#docs[@]}] $d 已验收，跳过"
      continue
    fi
    echo "[$index/${#docs[@]}] ===== $d 开始 ====="
    local max_attempt=1
    if [ "$SKIP_AFTER" -gt 0 ]; then max_attempt="$SKIP_AFTER"; fi
    local attempt=1
    local passed=0
    while [ "$attempt" -le "$max_attempt" ]; do
      if [ "$max_attempt" -gt 1 ]; then
        echo "--- ${d} 第 ${attempt}/${max_attempt} 次尝试  $(date '+%H:%M:%S') ---"
      fi
      if TIMEOUT="$TIMEOUT" bash scripts/graph_verify_one_document.sh "$d" "$MODEL"; then
        passed=1
        break
      fi
      attempt=$((attempt + 1))
    done
    if [ "$passed" -ne 1 ]; then
      if [ "$SKIP_AFTER" -gt 0 ]; then
        skipped_count=$((skipped_count + 1))
        skipped_list="$skipped_list $d"
        echo "⚠️ ${d} 连续 ${max_attempt} 次未完成 → 本轮跳过，记入待补跑清单，继续下一份。"
        continue
      fi
      echo ""
      echo "熔断于 ${d}。已完成结果全部保留；修好后重跑同一命令即断点续跑。"
      return 1
    fi
    echo "[$index/${#docs[@]}] ===== $d 完成 ====="
  done

  if [ "$skipped_count" -gt 0 ]; then
    local pending_dir="04_54份正式语料批处理/review_queue"
    mkdir -p "$pending_dir"
    local pending="$pending_dir/graph_pending_${MODEL_DIR}.md"
    {
      echo "# 图谱新增层待补跑清单（${MODEL}）"
      echo ""
      echo "- 生成时间：$(date '+%Y-%m-%d %H:%M:%S')"
      echo "- 本轮每份最多尝试 ${SKIP_AFTER} 次；仍未完成共 ${skipped_count} 份："
      echo ""
      for s in $skipped_list; do echo "- ${s}"; done
      echo ""
      echo "这些文档的 L0 底座表与已成功的 stage 响应均已保留；重跑同一条命令会自动跳过、只补未完成的调用。"
      echo ""
      echo "**本轮未全量，未执行统一导出 24 表，禁止导入 Neo4j；待上游恢复后重跑同一条命令补跑。**"
    } > "$pending"
    echo ""
    echo "⚠️ 本轮未完成全量：${skipped_count} 份待补跑（清单：${pending}）"
    echo "⚠️ 未执行统一导出 24 表，现有导入目录不得当作全量结果入库。"
    echo "   待上游恢复后重跑同一条命令即自动补跑这 ${skipped_count} 份。"
    return 0
  fi

  echo ""
  echo "===== 统一重导 24 表（合并全部已验收文档） ====="
  if ! python3 -u scripts/graph_export_import.py --model "$MODEL" --write; then
    echo "导出失败；单文档结果均保留。"
    return 1
  fi
  echo ""
  echo "===== 全部完成 ====="
  echo "结果目录：$OUT/"
  echo "图谱导入：05_合并与Neo4j/import_$MODEL_DIR/"
  echo "若出现疑似同一经历，清单在 04_54份正式语料批处理/review_queue/，"
  echo "按清单填写 human_adjudicated/$MODEL_DIR/life_episode_merges.csv 后重跑导出即可。"
  return 0
}

main "$@" 2>&1 | tee "$LOG"
exit "${PIPESTATUS[0]}"
