from pathlib import Path

from subtitle.ffmpeg import escape_filter_path


def test_escape_filter_path_escapes_ffmpeg_filter_chars():
    escaped = escape_filter_path(Path("C:/Video Dir/sub's.vi.ass"))

    assert escaped == "C\\:/Video Dir/sub\\'s.vi.ass"
