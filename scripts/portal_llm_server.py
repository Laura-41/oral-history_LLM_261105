#!/usr/bin/env python3
"""「归途」门户的本地问答代理：把离线检索好的因果链与逐字证据交给大模型组织语言。

用法（在工程根目录执行）：
    双击「一键启动大模型版.command」（最省事：自动启动 + 自动开浏览器）
    python3 scripts/portal_llm_server.py                # 同上，启动后自动打开浏览器
    python3 scripts/portal_llm_server.py --check        # 单次最小连通验证，不启动服务
    python3 scripts/portal_llm_server.py --no-browser   # 只启动服务，不开浏览器
    PORTAL_MODEL=cuc/qwen python3 scripts/portal_llm_server.py
    PORTAL_PORT=9000 python3 scripts/portal_llm_server.py
    双击「一键启动大模型版_手机预览.command」  # 同一 WiFi 下手机也能用真模型

密钥：单一专用来源，按显式配置择一，绝不自动回退批处理脚本的旧钥匙串条目：
      CUC_API_KEY_FILE（专用文件）｜ CUC_API_KEY（环境变量）｜ CUC_KEYCHAIN_SERVICE
      （默认 edu.cuc.openai.portal-key）。取不到就明确报缺，页面保持离线。
      密钥只在本进程内存里使用，不写入 归途·口述史记忆馆.html、不打印、不落盘。
      门户单文件是可分享的，绝不能内嵌密钥。
模型：cuc/qwen（默认）/ cuc/deepseek，页面可切换；cuc/qwen3-embedding 是向量检索模型，不用于对话。

设计口径：
  - 页面先在本地完成「检索 → 筛出真正能回答的事件 → 排因果链 → 取逐字原话」；
    代理只负责把这段上下文交给模型写成自然语言，不参与检索，也不改标注数据。
  - 模型输出里的 [n] 角标由页面转成引用按钮，来源卡片与离线模式完全相同。
  - 没启动代理、断网或调用失败时，页面自动回退离线回答，不留空白。
  - 默认监听 0.0.0.0、放行任意来源（便于转发给导师浏览），用日额度上限控制消耗：
    PORTAL_DAILY_LIMIT（默认 ¥80/天，按平台 token 定价折算），超额即停止并让页面回退离线。
    需收紧时设 PORTAL_BIND=127.0.0.1 + PORTAL_STRICT_ORIGIN=1。
  - 页面探测顺序：URL 参数 ?api=<代理地址> → 同源 → 127.0.0.1:8765 → localhost:8765。
    资料库里的静态副本要连公网代理，链接必须带 ?api=https://... （且代理对外可达）。
  - 默认模型 cuc/qwen；页面下拉可在 cuc/qwen 与 cuc/deepseek 之间切换（请求带 model，服务端白名单校验）。

"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_test import request_json  # noqa: E402  复用既有的请求封装

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "06_可视化原型"
PORTAL_FILE = "归途·口述史记忆馆.html"  # 门户单文件（中文名，便于手机预览识别）
BASE_URL = os.environ.get("CUC_BASE_URL", "https://openai.cuc.edu.cn/v1").rstrip("/")
MODEL = os.environ.get("PORTAL_MODEL", "cuc/qwen")   # 研究者 11-13 02:55 指定默认 qwen
CHAT_MODELS = ["cuc/deepseek", "cuc/qwen"]
PORT = int(os.environ.get("PORTAL_PORT", "8765"))
TIMEOUT = 90
# 该部署是带推理过程的模型：思考也会占 token，给太小会只返回 reasoning 而没有正文
MAX_TOKENS = int(os.environ.get("PORTAL_MAX_TOKENS", "2400"))
# 密钥来源可配置：CUC_API_KEY_FILE（专用文件路径）→ CUC_API_KEY 环境变量 → 钥匙串条目。
# 门户问答可与批处理脚本的钥匙串完全分开管理，三者都只在本进程内存里使用。
# 门户只读这一个专用钥匙串条目；绝不读批处理脚本用的 edu.cuc.openai.api-key。
# 研究者要求分开管理以便溯源、防止密钥混淆：取不到就明确报缺并保持离线。
KEYCHAIN_SERVICE = (os.environ.get("CUC_KEYCHAIN_SERVICE", "")
                    .strip() or "edu.cuc.openai.portal-key")
KEY_FILE = os.environ.get("CUC_API_KEY_FILE", "").strip()
_KEY_CACHE: str | None = None
_KEY_SOURCE = "未取到"
NO_BROWSER = os.environ.get("PORTAL_NO_BROWSER", "").strip().lower() in ("1", "true", "yes")
# 研究者 11-13 02:54 拍板：默认对外开放（便于转发给导师用手机浏览），靠日额度上限兜底。
# 想收回本机：PORTAL_BIND=127.0.0.1 PORTAL_STRICT_ORIGIN=1
LOCAL_ORIGIN = re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$")
BIND_HOST = os.environ.get("PORTAL_BIND", "").strip() or "0.0.0.0"
STRICT_ORIGIN = os.environ.get("PORTAL_STRICT_ORIGIN", "").strip().lower() in ("1", "true", "yes")
LAN_ORIGIN = re.compile(
    r"^https?://(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"
)
# 计价（¥ / 1M tokens，输入 / 输出）：平台定价页 cuc/qwen ¥3/¥18、cuc/deepseek ¥1/¥4
PRICE = {"cuc/deepseek": (1.0, 4.0), "cuc/qwen": (3.0, 18.0)}
DAILY_LIMIT = float(os.environ.get("PORTAL_DAILY_LIMIT", "80"))
USAGE_FILE = ROOT / ".workbuddy" / "portal_usage.json"   # 只记日期/次数/token/金额，不含密钥与提问内容
_USAGE_LOCK = threading.Lock()


def key_source() -> str:
    """只返回来源名称，绝不返回密钥内容，便于终端确认用的是哪条密钥。"""
    get_key()
    return _KEY_SOURCE


def _read_key_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line and line.lower().startswith(("cuc_api_key", "api_key")):
            line = line.split("=", 1)[1].strip().strip("\"'")
        return line.strip().strip("\"'")
    return ""


def get_key() -> str:
    """只读一个显式指定的专用来源；取不到就返回空，绝不回退旧密钥（溯源要求）。"""
    global _KEY_CACHE, _KEY_SOURCE
    if _KEY_CACHE is not None:
        return _KEY_CACHE
    key, source = "", "未取到"

    if KEY_FILE:
        path = Path(KEY_FILE).expanduser()
        try:
            key = _read_key_file(path) if path.is_file() else ""
        except (OSError, UnicodeDecodeError):
            key = ""
        source = f"专用文件 {path}" if key else f"专用文件 {path}（不存在或为空）"
    elif os.environ.get("CUC_API_KEY", "").strip():
        key = os.environ["CUC_API_KEY"].strip()
        source = "环境变量 CUC_API_KEY"
    elif sys.platform == "darwin":
        accounts = []
        for name in (os.environ.get("USER"), os.environ.get("LOGNAME"), getpass.getuser()):
            if name and name not in accounts:
                accounts.append(name)
        commands = [
            ["/usr/bin/security", "find-generic-password", "-a", a,
             "-s", KEYCHAIN_SERVICE, "-w"] for a in accounts
        ]
        commands.append(["/usr/bin/security", "find-generic-password",
                         "-s", KEYCHAIN_SERVICE, "-w"])
        for cmd in commands:
            try:
                result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, timeout=10)
                if result.returncode == 0 and result.stdout.strip():
                    key = result.stdout.strip()
                    break
            except (OSError, subprocess.SubprocessError):
                continue
        source = (f"钥匙串 {KEYCHAIN_SERVICE}" if key
                  else f"钥匙串 {KEYCHAIN_SERVICE}（未找到）")

    # 空值不缓存：补好专用密钥后不必重启代理即可生效
    _KEY_SOURCE = source
    if key:
        _KEY_CACHE = key
    return key

SYSTEM_PROMPT = """你是「归途」口述史记忆馆的回答助手。只能依据下面提供的访谈标注证据回答问题，不得引入外部知识，不得编造人物动机或史实。

要求：
1. 用中文自然语言直接回答用户的问题，2 到 4 段。先给结论或直接原因，再补前因与后续，像给人讲故事一样；不要列清单、不要 Markdown 标题、不要复述检索过程。
2. 每一个事实性论断后面用 [n] 标注依据编号，n 对应证据里的编号；同一段可以有多个角标。没有依据的话不要写。
3. 区分「受访者自述」与「标注整理」；时间只写证据里给出的说法，相对时间（如「五三惨案以后」）不要折算成绝对年份。
4. 若证据不足以回答，就直说「现有访谈里没有支撑这个说法的记录」，不要用常识补齐，也不要推测他没说过的心理。
5. 只输出回答正文，不要标题、解释、代码块或 JSON。"""


def build_user_prompt(body: dict) -> str:
    q = str(body.get("question", "")).strip()
    intent = str(body.get("intent", "overview"))
    focus = str(body.get("focus", ""))
    evidence = body.get("evidence", [])
    extras = body.get("extras", [])
    lines = [
        f"用户问题：{q}",
        f"问题类型：{ {'why': '追问原因，需要解释因果链', 'cross': '询问多人交集', 'overview': '询问经历概览'}.get(intent, '经历概览') }",
        f"焦点：{focus or '（未指定）'}",
        "",
        "检索到的依据链（已按前因 → 决定 → 行动筛过，按发生先后排序）：",
    ]
    if not isinstance(evidence, list) or not evidence:
        lines.append("（没有检索到可依据的事件记录）")
    for item in evidence[:8] if isinstance(evidence, list) else []:
        if not isinstance(item, dict):
            continue
        n = item.get("n", "?")
        lines.append(
            f"[{n}] 事件：{item.get('event', '')} ｜ 人物：{item.get('person', '')}"
            f" ｜ 时间：{item.get('time', '') or '时间待补'}"
            f" ｜ 地点：{'、'.join(item.get('places') or []) or '未标注'}"
        )
        if item.get("result"):
            lines.append(f"    结果状态：{item['result']}")
        causes = [x for x in (item.get("causes") or []) if x]
        purposes = [x for x in (item.get("purposes") or []) if x]
        if causes:
            lines.append("    因果标注（CAUSE）：" + "；".join(map(str, causes)))
        if purposes:
            lines.append("    目的（PURPOSE）：" + "；".join(map(str, purposes)))
        stages = [x for x in (item.get("stages") or []) if x]
        if stages:
            lines.append("    过程阶段：" + " → ".join(map(str, stages[:4])))
        for qi, quote in enumerate(item.get("quotes") or []):
            if qi >= 3:
                break
            lines.append(f"    逐字原话{qi + 1}：{str(quote)[:420]}")
    if extras:
        lines.append("")
        lines.append("以下记录与问题沾边，但不直接回答问题，不要拿来凑数：" + "；".join(map(str, extras[:6])))
    lines += ["", "请据此写一段有依据的中文回答，记得在事实性论断后标 [n]。"]
    return "\n".join(lines)


def extract_text(data: dict) -> str:
    """只取正式回答正文；content=null 且只有 reasoning 时明确报错，绝不把思考过程给用户。"""
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"返回结构异常：{list(data)[:6]}") from exc
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    text = "" if content is None else str(content).strip()
    if not text:
        raise RuntimeError("模型只返回了推理过程、没有生成正文；可增大 PORTAL_MAX_TOKENS 或换 cuc/qwen")
    return text


def sanitize_error(exc: Exception, api_key: str) -> str:
    text = str(exc)
    if api_key and api_key in text:
        text = text.replace(api_key, "***")
    return text[:260]


def _load_usage() -> dict:
    try:
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _day_usage(data: dict) -> dict:
    d = data.get(_today())
    if not isinstance(d, dict):
        d = {}
    return {"cost": float(d.get("cost", 0)), "calls": int(d.get("calls", 0)),
            "tokens": int(d.get("tokens", 0))}


def budget_status() -> dict:
    with _USAGE_LOCK:
        u = _day_usage(_load_usage())
    return {"date": _today(), "limit": DAILY_LIMIT, "used": round(u["cost"], 4),
            "remaining": round(max(0.0, DAILY_LIMIT - u["cost"]), 4), "calls": u["calls"]}


def _check_budget():
    u = _day_usage(_load_usage())
    if u["cost"] >= DAILY_LIMIT:
        raise RuntimeError(
            f"今日问答额度已用满（¥{DAILY_LIMIT:g}/天），请明天再试或调高 PORTAL_DAILY_LIMIT"
        )


def _record_usage(model: str, usage: dict):
    """按平台定价折算金额并落账；并发下为软上限（检查与记账之间的请求可能略超）。"""
    pt = int((usage or {}).get("prompt_tokens") or 0)
    ct = int((usage or {}).get("completion_tokens") or 0)
    tt = int((usage or {}).get("total_tokens") or (pt + ct))
    if not tt:  # 上游未返回 usage 时按一次约 2000 tokens 保守计
        pt, ct, tt = 1500, 500, 2000
    pin, pout = PRICE.get(model, PRICE["cuc/qwen"])
    cost = (pt * pin + ct * pout) / 1_000_000
    with _USAGE_LOCK:
        data = _load_usage()
        d = _day_usage(data)
        data[_today()] = {"cost": round(d["cost"] + cost, 6),
                          "calls": d["calls"] + 1, "tokens": d["tokens"] + tt}
        try:
            USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"[portal] 额度账本写入失败：{exc}", flush=True)


def ask_model(body: dict) -> dict:
    api_key = get_key()
    if not api_key:
        raise RuntimeError("未取到 CUC_API_KEY（可设置环境变量，或授权 macOS 钥匙串）")
    model = str(body.get("model") or MODEL).strip()
    if model not in CHAT_MODELS:
        raise RuntimeError(f"{model} 不是对话模型；可选 {' / '.join(CHAT_MODELS)}")
    _check_budget()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(body)},
        ],
        "temperature": 0.3,
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    data = request_json(
        method="POST",
        url=f"{BASE_URL}/chat/completions",
        api_key=api_key,
        payload=payload,
        timeout=TIMEOUT,
    )
    result = {"ok": True, "text": extract_text(data), "model": model,
              "usage": data.get("usage", {})}
    _record_usage(model, data.get("usage"))
    return result


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def log_message(self, fmt, *args):
        # 只记方法/路径/状态，避免把请求体或密钥写进终端日志
        print(f"[portal] {self.address_string()} {fmt % args}", flush=True)

    def _cors_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return None
        if not STRICT_ORIGIN:
            return origin  # 默认开放：任意来源都可问答，用量由日额度上限约束
        if origin == "null" or LOCAL_ORIGIN.match(origin) or LAN_ORIGIN.match(origin):
            return origin
        host = (self.headers.get("Host") or "").split(":")[0]
        m = re.match(r"^https?://([^/:]+)", origin)
        if host and m and m.group(1) == host:
            return origin
        return None

    def _reject_foreign_origin(self):
        """严格模式下才拒绝外部来源；默认开放，由日额度上限控制消耗。"""
        if self.headers.get("Origin") and not self._cors_origin():
            self._json(403, {"ok": False, "error": "拒绝非本机来源的调用"})
            return True
        return False

    def _json(self, code: int, obj: dict):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        """跨域预检：file:// 或其它本机静态预览页面 POST /api/ask 前会先问一次。"""
        origin = self._cors_origin()
        self.send_response(204 if origin else 403)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/api/status":
            if self._reject_foreign_origin():
                return
            key = get_key()
            self._json(200, {
                "ok": bool(key) and MODEL in CHAT_MODELS,
                "model": MODEL,
                "models": CHAT_MODELS,
                "base": BASE_URL,
                "key": bool(key),
                "budget": budget_status(),
            })
            return
        # 门户单文件已改为中文名：根目录与旧 /index.html 书签都指向它
        if self.path.split("?", 1)[0] in ("/", "/index.html"):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            self.path = "/" + quote(PORTAL_FILE) + ("?" + query if query else "")
        super().do_GET()

    def do_POST(self):
        if self._reject_foreign_origin():
            return
        if self.path.split("?")[0] != "/api/ask":
            self._json(404, {"ok": False, "error": "未知接口"})
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 200_000)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(400, {"ok": False, "error": f"请求体不是合法 JSON：{exc}"})
            return
        t0 = time.time()
        try:
            result = ask_model(body)
            result["elapsed"] = round(time.time() - t0, 1)
            self._json(200, result)
        except Exception as exc:  # noqa: BLE001  失败一律回退离线，页面不报错卡住
            self._json(502, {"ok": False, "error": sanitize_error(exc, get_key() or "")})


def lan_ip() -> str:
    """取本机局域网 IP（UDP connect 不实际发包），用于打印手机访问地址。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.168.1.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def check_once() -> int:
    key = get_key()
    print(f"密钥：{'已取到（内容不显示）' if key else '未取到'} ｜ 来源：{key_source()}")
    print(f"接口：{BASE_URL}/chat/completions ｜ 模型：{MODEL}")
    if not key:
        print(f"提示：请配置专用密钥：CUC_API_KEY_FILE 文件、CUC_API_KEY 环境变量，"
              f"或钥匙串条目 {KEYCHAIN_SERVICE}（不回退旧条目）")
        return 2
    t0 = time.time()
    try:
        data = request_json(
            method="POST",
            url=f"{BASE_URL}/chat/completions",
            api_key=key,
            payload={"model": MODEL,
                     "messages": [{"role": "user", "content": "你好，只回复两个字：连通"}],
                     "max_tokens": 512, "stream": False},
            timeout=45,
        )
        content = extract_text(data)
        print(f"连通成功：{content[:40]} ｜ 耗时 {time.time() - t0:.1f}s "
              f"｜ tokens {data.get('usage', {}).get('total_tokens', '?')}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print("连通失败：" + sanitize_error(exc, key))
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="门户问答本地代理（密钥不进页面）")
    ap.add_argument("--check", action="store_true", help="只做一次最小连通验证，不启动服务")
    ap.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = ap.parse_args()
    if args.check:
        return check_once()
    if not SITE_DIR.is_dir():
        print(f"找不到门户目录：{SITE_DIR}")
        return 2
    if not (SITE_DIR / PORTAL_FILE).is_file():
        print(f"提示：未找到 {PORTAL_FILE}，请先在工程根执行 python3 scripts/build_user_portal.py")
    server = ThreadingHTTPServer((BIND_HOST, PORT), Handler)
    print(f"门户已启动：http://127.0.0.1:{PORT}/")
    b = budget_status()
    print(f"今日额度：已用 ¥{b['used']} / ¥{b['limit']}（{b['calls']} 次问答）｜ 可用 PORTAL_DAILY_LIMIT 调整")
    ip = lan_ip()
    if ip:
        print(f"同一 WiFi 的手机可打开：http://{ip}:{PORT}/")
    key_ok = bool(get_key())
    print(f"模型：{MODEL} ｜ 密钥：{'已取到' if key_ok else '未取到（页面会保持离线回答）'}"
          f" ｜ 来源：{key_source()}")
    if not key_ok:
        print("提示：门户只读专用密钥来源，绝不回退批处理脚本的旧条目；请先配置专用密钥。")
    print("页面自动检测代理：可用即切换大模型，失败自动回退离线回答。")
    print("双击「归途·口述史记忆馆.html」也能连上；按 Ctrl+C 或关闭窗口即停止。")
    if not (args.no_browser or NO_BROWSER):
        url = f"http://127.0.0.1:{PORT}/"
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        print(f"已自动打开浏览器：{url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
