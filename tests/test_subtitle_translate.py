import pytest

from cli.subtitle_commands import _run_translate_srt
from subtitle.errors import TranslationError
from subtitle.srt_parser import parse_srt_text
from subtitle.translator import translate_cues
from subtitle.translators.noop import NoopTranslator


class _SuffixTranslator:
    def translate_texts(self, items, *, source_lang, target_lang):
        return [
            {"id": item["id"], "text": f"{item['text']} [{target_lang}]"}
            for item in items
        ]


class _MissingTranslator:
    def translate_texts(self, items, *, source_lang, target_lang):
        return []


def test_noop_translator_keeps_text_and_timing():
    cues = parse_srt_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n")

    translated = translate_cues(
        cues,
        NoopTranslator(),
        source_lang="zh",
        target_lang="vi",
    )

    assert translated == cues


def test_translate_cues_preserves_timestamp_and_index():
    cues = parse_srt_text(
        "1\n00:00:01,000 --> 00:00:02,000\n你好\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n世界\n"
    )

    translated = translate_cues(
        cues,
        _SuffixTranslator(),
        source_lang="zh",
        target_lang="vi",
        batch_size=1,
    )

    assert [cue.index for cue in translated] == [1, 2]
    assert [cue.start_ms for cue in translated] == [1000, 3000]
    assert [cue.end_ms for cue in translated] == [2000, 4000]
    assert translated[0].text == "你好 [vi]"


def test_translate_cues_rejects_missing_id():
    cues = parse_srt_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n")

    with pytest.raises(TranslationError):
        translate_cues(cues, _MissingTranslator(), source_lang="zh", target_lang="vi")


def test_translate_srt_cli_preserves_line_breaks_by_default(tmp_path):
    input_path = tmp_path / "input.srt"
    output_path = tmp_path / "output.srt"
    input_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nA\nB\n",
        encoding="utf-8",
    )

    class _Display:
        def print_success(self, _message):
            return None

    args = type(
        "Args",
        (),
        {
            "input": str(input_path),
            "output": str(output_path),
            "translator": "noop",
            "source_lang": "zh",
            "target_lang": "vi",
            "batch_size": 20,
            "no_preserve_line_breaks": False,
        },
    )()

    _run_translate_srt(args, _Display())

    assert "A\nB" in output_path.read_text(encoding="utf-8")
