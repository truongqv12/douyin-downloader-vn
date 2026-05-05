from pathlib import Path

from subtitle.batch import (
    build_batch_items,
    discover_video_paths,
    find_matching_srt,
    output_paths_for_item,
    output_subtitle_paths_for_item,
    parse_csv_values,
    run_subtitle_batch,
)


def test_parse_csv_values_uses_defaults_for_empty_input():
    assert parse_csv_values("", [".mp4"]) == [".mp4"]
    assert parse_csv_values(".mp4, .mov", []) == [".mp4", ".mov"]


def test_discover_video_paths_recurses_and_filters_extensions(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"video")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.MOV").write_bytes(b"video")
    (nested / "note.txt").write_text("ignore", encoding="utf-8")

    videos = discover_video_paths(directory=tmp_path)

    assert videos == [tmp_path / "a.mp4", nested / "b.MOV"]


def test_find_matching_srt_prefers_transcript_suffix(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    transcript = tmp_path / "clip.transcript.srt"
    plain = tmp_path / "clip.srt"
    transcript.write_text("transcript", encoding="utf-8")
    plain.write_text("plain", encoding="utf-8")

    assert find_matching_srt(video).read_text(encoding="utf-8") == "transcript"


def test_build_batch_items_skips_missing_srt_and_existing_output(tmp_path):
    output_dir = tmp_path / "out"
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    third = tmp_path / "third.mp4"
    for video in (first, second, third):
        video.write_bytes(b"video")
    (first.with_suffix(".transcript.srt")).write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")
    (third.with_suffix(".srt")).write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")
    existing = output_dir / "third" / "third.vi.mp4"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"done")

    items = build_batch_items(
        directory=tmp_path,
        output_dir=output_dir,
        target_lang="vi",
        skip_existing=True,
    )

    by_name = {item.video_path.name: item for item in items}
    assert by_name["first.mp4"].srt_path == tmp_path / "first.transcript.srt"
    assert by_name["second.mp4"].skip_reason == "matching srt not found"
    assert by_name["third.mp4"].skip_reason == "output video already exists"


def test_build_batch_items_skip_existing_no_burn_checks_srt_and_ass(tmp_path):
    output_dir = tmp_path / "out"
    video = tmp_path / "clip.mp4"
    srt = tmp_path / "clip.transcript.srt"
    video.write_bytes(b"video")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")
    item_output_dir, _output_video_path = output_paths_for_item(
        video_path=video,
        base_dir=tmp_path,
        output_dir=output_dir,
        target_lang="vi",
    )
    output_srt, output_ass = output_subtitle_paths_for_item(
        srt_path=srt,
        output_dir=item_output_dir,
        target_lang="vi",
    )
    output_srt.parent.mkdir(parents=True)
    output_srt.write_text("done", encoding="utf-8")
    output_ass.write_text("done", encoding="utf-8")

    items = build_batch_items(
        directory=tmp_path,
        output_dir=output_dir,
        target_lang="vi",
        skip_existing=True,
        burn=False,
    )

    assert len(items) == 1
    assert items[0].skip_reason == "translated srt and ass already exist"


def test_output_paths_can_preserve_nested_tree(tmp_path):
    video = tmp_path / "nested" / "day1" / "clip.mp4"
    output_dir = tmp_path / "out"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")

    item_output_dir, output_video_path = output_paths_for_item(
        video_path=video,
        base_dir=tmp_path,
        output_dir=output_dir,
        target_lang="vi",
        preserve_tree=True,
    )

    assert item_output_dir == output_dir / "nested" / "day1" / "clip"
    assert output_video_path == item_output_dir / "clip.vi.mp4"


def test_run_subtitle_batch_no_burn_processes_available_srt(tmp_path):
    video = tmp_path / "clip.mp4"
    srt = tmp_path / "clip.transcript.srt"
    output_dir = tmp_path / "out"
    video.write_bytes(b"video")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")

    summary = run_subtitle_batch(
        directory=tmp_path,
        output_dir=output_dir,
        translator_name="noop",
        burn=False,
    )

    assert summary.total == 1
    assert summary.success == 1
    result = summary.results[0]
    assert result.status == "success"
    assert Path(result.outputs["translated_srt"]).exists()
    assert Path(result.outputs["ass"]).exists()
