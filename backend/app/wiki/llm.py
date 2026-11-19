"""LLM 桥接：给 Wiki 引擎用的最小同步客户端。

设计取向：
- 只依赖 OpenAI 兼容协议（OpenAI / DeepSeek / Ollama / vLLM / 自建网关都能用）
- 未配置模型时 `available()` 返回 False，调用方必须走确定性降级路径，
  这样「没配 Key 也能把资料编译成 wiki」这件事是产品能力，而不是异常分支。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


class LLMBridge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = (settings.llm_provider or "none").lower().strip()

    def available(self) -> bool:
        if self.provider in {"", "none", "off"}:
            return False
        if self.provider == "ollama":
            return True
        return bool(self.settings.llm_api_key)

    def model(self) -> str:
        if self.settings.llm_model:
            return self.settings.llm_model
        return "qwen2.5:7b" if self.provider == "ollama" else "gpt-4o-mini"

    def base_url(self) -> str:
        if self.settings.llm_base_url:
            return self.settings.llm_base_url.rstrip("/")
        if self.provider == "ollama":
            return "http://127.0.0.1:11434/v1"
        return "https://api.openai.com/v1"

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float = 240.0,
    ) -> str:
        if not self.available():
            raise LLMUnavailable("未配置可用的 LLM（LLM_PROVIDER / LLM_API_KEY）")
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        payload = {
            "model": self.model(),
            "messages": messages,
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or max(1200, self.settings.llm_max_tokens),
            "stream": False,
        }
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{self.base_url()}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"LLM 返回结构异常：{exc}") from exc

    def json_object(self, prompt: str, *, max_tokens: int = 1500) -> dict[str, Any]:
        raw = self.chat(
            [
                {"role": "system", "content": "你只输出严格合法的 JSON，不要任何解释、不要 markdown 代码围栏。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return parse_json_loose(raw)

    def health(self) -> dict[str, Any]:
        return {
            "available": self.available(),
            "provider": self.provider,
            "model": self.model() if self.available() else None,
        }


def parse_json_loose(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"items": data}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {"items": data}
        except json.JSONDecodeError:
            pass
    return {}
