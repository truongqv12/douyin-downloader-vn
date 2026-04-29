from __future__ import annotations

from typing import Dict, List, Protocol, Sequence

from .errors import TranslationError
from .models import SubtitleCue
from .srt_parser import validate_same_timing


class Translator(Protocol):
    def translate_texts(
        self,
        items: Sequence[Dict[str, str]],
        *,
        source_lang: str,
        target_lang: str,
    ) -> List[Dict[str, str]]:
        ...


def create_translator(name: str) -> Translator:
    normalized = (name or "noop").strip().lower()
    if normalized == "noop":
        from .translators.noop import NoopTranslator

        return NoopTranslator()
    if normalized == "argos":
        from .translators.argos import ArgosTranslator

        return ArgosTranslator()
    if normalized == "ollama":
        from .translators.ollama import OllamaTranslator

        return OllamaTranslator()
    raise TranslationError(f"unsupported translator backend: {name}")


def translate_cues(
    cues: Sequence[SubtitleCue],
    translator: Translator,
    *,
    source_lang: str,
    target_lang: str,
    batch_size: int = 20,
    preserve_line_breaks: bool = True,
) -> List[SubtitleCue]:
    batch_size = max(1, int(batch_size or 1))
    output: List[SubtitleCue] = []

    for start in range(0, len(cues), batch_size):
        batch = cues[start : start + batch_size]
        items = [
            {
                "id": str(cue.index),
                "text": _prepare_text(cue.text, preserve_line_breaks=preserve_line_breaks),
            }
            for cue in batch
        ]
        translated = translator.translate_texts(
            items,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        mapped = _map_translated_items(translated)
        for cue in batch:
            key = str(cue.index)
            if key not in mapped:
                raise TranslationError(f"translator did not return cue id={key}")
            output.append(cue.with_text(mapped[key]))

    validate_same_timing(cues, output)
    return output


def _prepare_text(text: str, *, preserve_line_breaks: bool) -> str:
    if preserve_line_breaks:
        return text or ""
    return " ".join(str(text or "").splitlines())


def _map_translated_items(items: Sequence[Dict[str, str]]) -> Dict[str, str]:
    mapped: Dict[str, str] = {}
    for item in items:
        key = str(item.get("id", "")).strip()
        if not key:
            raise TranslationError("translator returned item without id")
        mapped[key] = str(item.get("text", ""))
    return mapped
