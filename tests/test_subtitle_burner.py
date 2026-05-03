from pathlib import Path

import pytest

from subtitle import burner


def test_build_subtitle_filter_includes_fontsdir():
    value = burner.build_subtitle_filter(Path("sub.vi.ass"), fonts_dir="fonts")

    assert value == "subtitles='sub.vi.ass':fontsdir='fonts'"


def test_build_burn_command(monkeypatch):
    monkeypatch.setattr(burner, "find_ffmpeg", lambda _path="": "ffmpeg")

    command = burner.build_burn_command(
        video_path=Path("input.mp4"),
        ass_path=Path("sub.vi.ass"),
        output_path=Path("out.mp4"),
        crf=20,
        preset="fast",
    )

    assert command[:5] == ["ffmpeg", "-y", "-i", "input.mp4", "-vf"]
    assert "subtitles='sub.vi.ass'" in command
    assert command[-1] == "out.mp4"


def test_burn_ass_smoke_if_ffmpeg_available(tmp_path):
    pytest.importorskip("shutil")
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")

    video = tmp_path / "input.mp4"
    ass = tmp_path / "sub.ass"
    output = tmp_path / "out.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=0.5",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    ass.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:00.40,Default,,0,0,0,,Xin chao\n",
        encoding="utf-8",
    )

    burner.burn_ass(video_path=video, ass_path=ass, output_path=output)

    assert output.exists()
