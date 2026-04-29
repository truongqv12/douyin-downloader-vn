from __future__ import annotations

from typing import Dict, List, Sequence

from subtitle.errors import DependencyUnavailableError, TranslationError


class ArgosTranslator:
    def __init__(self):
        try:
            import argostranslate.translate as argos_translate
        except ImportError:
            raise DependencyUnavailableError(
                "argos-translate is not installed. Install optional dependency: "
                "pip install argos-translate"
            )
        self._argos_translate = argos_translate

    def translate_texts(
        self,
        items: Sequence[Dict[str, str]],
        *,
        source_lang: str,
        target_lang: str,
    ) -> List[Dict[str, str]]:
        from_lang = self._find_language(source_lang)
        to_lang = self._find_language(target_lang)
        translation = from_lang.get_translation(to_lang)
        if translation is None:
            raise TranslationError(
                f"Argos package for {source_lang}->{target_lang} is not installed"
            )
        return [
            {"id": item["id"], "text": translation.translate(item.get("text", ""))}
            for item in items
        ]

    def _find_language(self, code: str):
        normalized = (code or "").strip().lower()
        for language in self._argos_translate.get_installed_languages():
            if getattr(language, "code", "").lower() == normalized:
                return language
        raise TranslationError(f"Argos language package is not installed: {code}")
