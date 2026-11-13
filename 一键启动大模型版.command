#!/bin/bash
# 「归途 · 口述史记忆馆」一键启动：启动本机问答代理并自动打开浏览器。
# 双击本文件即可；用完按 Ctrl+C 或直接关闭这个终端窗口就会停止。
# 网页文件本身永远不变：不跑本脚本 = 离线版，跑了 = 真大模型回答。
# 默认模型 cuc/qwen（页面里可切到 cuc/deepseek）；默认对外开放，按同一 WiFi 的手机地址见下方。
# 每日额度上限 ¥80；如需调整，取消下一行注释并改数字：
# export PORTAL_DAILY_LIMIT=120
# 想换默认模型：export PORTAL_MODEL=cuc/deepseek

cd "$(dirname "$0")" || exit 1

# 门户问答专用密钥条目：与批处理脚本的 edu.cuc.openai.api-key 完全分开。
# 严格只用这一个来源，取不到就保持离线，绝不回退旧条目（便于溯源、防止混淆）。
export CUC_KEYCHAIN_SERVICE="edu.cuc.openai.portal-key"

# 也可以改用单独管理的密钥文件，取消下一行注释并填绝对路径：
# export CUC_API_KEY_FILE="$HOME/你的密钥目录/api_key.txt"
# 或者改用另一个钥匙串条目：export CUC_KEYCHAIN_SERVICE="你的条目名"

echo "=============================================="
echo "  归途 · 口述史记忆馆 ｜ 大模型问答"
echo "=============================================="
echo "正在启动本机代理…（密钥只留在本机，绝不写进网页）"
LAN_IP=$(python3 -c 'import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(("192.168.1.1",9));print(s.getsockname()[0])' 2>/dev/null)
[ -n "$LAN_IP" ] && echo "同一 WiFi 的手机可打开： http://${LAN_IP}:8765/"
echo "默认模型 cuc/qwen ｜ 每日额度上限 ¥80 ｜ 页面里可切换模型"
echo

if curl -fsS --max-time 1 http://127.0.0.1:8765/api/status >/dev/null 2>&1; then
  echo "代理已经在运行，直接为你打开页面。"
  open "http://127.0.0.1:8765/"
  sleep 2
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 python3，请先安装 Python 3 再双击本文件。"
  read -r -p "按回车关闭…" _
  exit 1
fi

exec python3 -u scripts/portal_llm_server.py
