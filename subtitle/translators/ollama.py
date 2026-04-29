from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Sequence
from urllib import request

from subtitle.errors import TranslationError


class OllamaTranslator:
    def __init__(self, base_url: str = "", model: str = ""):
        self.base_url = (base_url or os.getenv("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL") or "qwen2.5:7b"

    def translate_texts(
        self,
        items: Sequence[Dict[str, str]],
        *,
        source_lang: str,
        target_lang: str,
    ) -> List[Dict[str, str]]:
        prompt = self._build_prompt(items, source_lang=source_lang, target_lang=target_lang)
        payload = json.dumps(
            {"model": self.model, "prompt": prompt, "stream": False},
            ensure_ascii=False,
        ).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise TranslationError(f"Ollama translation request failed: {exc}")

        content = str(body.get("response", "")).strip()
        return self._parse_response(content)

    @staticmethod
    def _build_prompt(
        items: Sequence[Dict[str, str]],
        *,
        source_lang: str,
        target_lang: str,
    ) -> str:
        # Chỉ gửi id/text để LLM không có cơ hội sửa timestamp của subtitle gốc.
        return (
            "Translate subtitle texts from "
            f"{source_lang} to {target_lang}. Return JSON array only. "
            "Keep each id unchanged. Do not add commentary. Input:\n"
            f"{json.dumps(list(items), ensure_ascii=False)}"
        )

    @staticmethod
    def _parse_response(content: str) -> List[Dict[str, str]]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"(\[[\s\S]*\])", content)
            if not match:
                raise TranslationError("Ollama response is not JSON array")
            data = json.loads(match.group(1))
        if not isinstance(data, list):
            raise TranslationError("Ollama response must be a JSON array")
        out: List[Dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                raise TranslationError("Ollama response items must be objects")
            out.append({"id": str(item.get("id", "")), "text": str(item.get("text", ""))})
        return out
