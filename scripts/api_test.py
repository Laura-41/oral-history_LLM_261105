#!/usr/bin/env python3
"""中国传媒大学 OpenAI 兼容接口的最小安全测试。

密钥只从环境变量 CUC_API_KEY 读取，不写入文件和日志。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "https://openai.cuc.edu.cn/v1"


def request_json(
    *,
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    data = None
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"连接失败：{exc.reason}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"接口没有返回合法JSON：{body[:1000]}") from exc


def list_models(base_url: str, api_key: str) -> list[str]:
    result = request_json(
        method="GET",
        url=f"{base_url}/models",
        api_key=api_key,
    )
    model_ids = [
        str(item.get("id"))
        for item in result.get("data", [])
        if item.get("id")
    ]
    print("\n[1/3] API认证和模型列表：成功")
    if model_ids:
        for model_id in model_ids:
            print(f"  - {model_id}")
    else:
        print("  接口已连接，但返回结果中没有发现 data[].id。")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return model_ids


def chat_test(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是口述史资料标注助手。"},
            {"role": "user", "content": "只回答：API测试成功"},
        ],
        "temperature": 0,
        "stream": False,
    }
    result = request_json(
        method="POST",
        url=f"{base_url}/chat/completions",
        api_key=api_key,
        payload=payload,
    )
    content = extract_content(result)
    print(f"\n[2/3] {model} 中文响应：成功")
    print(f"  内容：{content}")
    print_usage(result)
    return result


def json_test(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是信息抽取程序。只输出一个合法JSON对象，不要输出Markdown或解释。",
            },
            {
                "role": "user",
                "content": (
                    "原文：1931年他到上海印书馆做排字工人。"
                    "请输出字段 event_name、event_type、process、participants、time、place。"
                    "event_type必须从物质、心理、关系、言语、行为、存在中选择。"
                ),
            },
        ],
        "temperature": 0,
        "stream": False,
    }
    result = request_json(
        method="POST",
        url=f"{base_url}/chat/completions",
        api_key=api_key,
        payload=payload,
    )
    content = extract_content(result).strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    print(f"\n[3/3] {model} JSON输出测试")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        print("  结果：失败，模型内容不是合法JSON。")
        print(f"  模型原始内容：{content}")
    else:
        print("  结果：成功，模型内容可以解析为JSON。")
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    print_usage(result)
    return result


def extract_content(result: dict[str, Any]) -> str:
    try:
        return str(result["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "响应中找不到 choices[0].message.content：\n"
            + json.dumps(result, ensure_ascii=False, indent=2)[:3000]
        ) from exc


def print_usage(result: dict[str, Any]) -> None:
    usage = result.get("usage")
    if usage:
        print("  Token统计：" + json.dumps(usage, ensure_ascii=False))
    else:
        print("  Token统计：响应中未提供 usage 字段，请查看学校平台使用日志。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="学校大模型API连通测试")
    parser.add_argument(
        "--mode",
        choices=("models", "chat", "json", "all"),
        default="models",
        help="测试项目；第一次建议只运行 models。",
    )
    parser.add_argument(
        "--model",
        default="cuc/deepseek",
        help="chat/json测试使用的模型ID。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = os.environ.get("CUC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    api_key = os.environ.get("CUC_API_KEY", "").strip()
    if not api_key:
        print("错误：没有检测到 CUC_API_KEY。", file=sys.stderr)
        print("请先按照工作流程文档，在当前终端隐藏输入并导出密钥。", file=sys.stderr)
        return 2

    try:
        if args.mode in {"models", "all"}:
            list_models(base_url, api_key)
        if args.mode in {"chat", "all"}:
            chat_test(base_url, api_key, args.model)
        if args.mode in {"json", "all"}:
            json_test(base_url, api_key, args.model)
    except RuntimeError as exc:
        print(f"\n测试失败：{exc}", file=sys.stderr)
        return 1

    print("\n测试结束。程序没有保存或打印API密钥。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

