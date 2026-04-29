from subtitle.ass_converter import escape_ass_text, format_ass
from subtitle.srt_parser import parse_srt_text
from subtitle.style import AssStyle


def test_format_ass_contains_style_and_dialogue():
    cues = parse_srt_text("1\n00:00:01,000 --> 00:00:02,500\nXin chào\n")
    style = AssStyle(font="Noto Sans", font_size=42, margin_v=70)

    ass = format_ass(cues, style)

    assert "[V4+ Styles]" in ass
    assert "Style: Default,Noto Sans,42" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:02.50,Default" in ass
    assert "Xin chào" in ass


def test_escape_ass_text_handles_newlines_and_override_chars():
    text = "A{tag}\\B\nC}"

    escaped = escape_ass_text(text)

    assert escaped == "A\\{tag\\}\\\\B\\NC\\}"


def test_style_from_config_applies_preset_and_overrides():
    config = {
        "style": {
            "presets": {
                "douyin_vi": {
                    "font": "Arial",
                    "font_size": 36,
                    "margin_v": 80,
                }
            }
        }
    }

    style = AssStyle.from_config(
        config,
        preset_name="douyin_vi",
        overrides={"font_size": 44},
    )

    assert style.font == "Arial"
    assert style.font_size == 44
    assert style.margin_v == 80


def test_style_from_config_preserves_explicit_zero_values():
    config = {
        "style": {
            "presets": {
                "douyin_vi": {
                    "shadow": 0,
                    "outline": 0,
                    "margin_v": 0,
                    "spacing": 0,
                }
            }
        }
    }

    style = AssStyle.from_config(config, preset_name="douyin_vi")

    assert style.shadow == 0
    assert style.outline == 0
    assert style.margin_v == 0
    assert style.spacing == 0
