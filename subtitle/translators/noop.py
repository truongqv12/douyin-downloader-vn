from __future__ import annotations

from typing import Dict, List, Sequence


class NoopTranslator:
    def translate_texts(
        self,
        items: Sequence[Dict[str, str]],
        *,
        source_lang: str,
        target_lang: str,
    ) -> List[Dict[str, str]]:
        return [{"id": item["id"], "text": item.get("text", "")} for item in items]
