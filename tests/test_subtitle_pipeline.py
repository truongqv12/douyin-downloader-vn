from pathlib import Path

from subtitle.pipeline import SubtitlePipeline


def test_subtitle_pipeline_no_burn_creates_srt_and_ass(tmp_path):
    srt = tmp_path / "input.srt"
    video = tmp_path / "input.mp4"
    out_dir = tmp_path / "out"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")
    video.write_bytes(b"not-a-real-video")

    result = SubtitlePipeline().run(
        video_path=video,
        input_srt_path=srt,
        output_video_path=None,
        output_dir=out_dir,
        translator_name="noop",
        burn=False,
    )

    assert result.status == "success"
    translated = Path(result.outputs["translated_srt"])
    ass = Path(result.outputs["ass"])
    assert translated.exists()
    assert ass.exists()
    assert "Dialogue:" in ass.read_text(encoding="utf-8")


def test_subtitle_pipeline_reports_failure(tmp_path):
    result = SubtitlePipeline().run(
        video_path=tmp_path / "missing.mp4",
        input_srt_path=tmp_path / "missing.srt",
        output_video_path=None,
        output_dir=tmp_path,
        burn=False,
    )

    assert result.status == "failed"
    assert "FileNotFoundError" in result.error
    assert result.stage == "parse"


def test_subtitle_pipeline_reports_failure_stage(tmp_path):
    srt = tmp_path / "input.srt"
    video = tmp_path / "input.mp4"
    out_dir = tmp_path / "out"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")
    video.write_bytes(b"not-a-real-video")

    result = SubtitlePipeline().run(
        video_path=video,
        input_srt_path=srt,
        output_video_path=None,
        output_dir=out_dir,
        translator_name="noop",
        burn=True,
        mask_mode="box",
        mask_rect=None,
    )

    assert result.status == "failed"
    assert result.stage == "burn"
    assert "mask rect is required" in result.error
