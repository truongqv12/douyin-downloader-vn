from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from subtitle.ass_converter import convert_srt_to_ass
from subtitle.burner import burn_ass
from subtitle.mask import build_masked_subtitle_filter
from subtitle.models import MaskRect
from subtitle.pipeline import SubtitlePipeline
from subtitle.roi_picker import pick_mask_rect
from subtitle.srt_parser import parse_srt, validate_same_timing, write_srt
from subtitle.style import AssStyle
from subtitle.translator import create_translator, translate_cues


def add_subtitle_subcommands(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="subtitle_command")

    translate = subparsers.add_parser(
        "translate-srt",
        help="Dịch SRT nhưng giữ nguyên timestamp",
    )
    translate.add_argument("--input", required=True, help="File SRT đầu vào")
    translate.add_argument("--output", required=True, help="File SRT đã dịch")
    translate.add_argument("--source-lang", default="zh", help="Ngôn ngữ nguồn")
    translate.add_argument("--target-lang", default="vi", help="Ngôn ngữ đích")
    translate.add_argument(
        "--translator",
        default="noop",
        choices=["noop", "argos", "ollama"],
        help="Backend dịch",
    )
    translate.add_argument("--batch-size", type=int, default=20, help="Số cue mỗi batch")
    translate.add_argument(
        "--preserve-line-breaks",
        action="store_true",
        help="Giữ xuống dòng trong từng cue khi gửi đi dịch",
    )

    convert = subparsers.add_parser(
        "srt-to-ass",
        help="Convert SRT sang ASS với style preset",
    )
    convert.add_argument("--input", required=True, help="File SRT đầu vào")
    convert.add_argument("--output", required=True, help="File ASS đầu ra")
    convert.add_argument("--style-preset", default="douyin_vi", help="Tên style preset")
    convert.add_argument("--font", default=None, help="Font subtitle")
    convert.add_argument("--font-size", type=int, default=None, help="Cỡ chữ")
    convert.add_argument("--alignment", type=int, default=None, help="ASS alignment")
    convert.add_argument("--margin-v", type=int, default=None, help="Margin dọc")
    convert.add_argument("--outline", type=int, default=None, help="Độ dày outline")
    convert.add_argument("--shadow", type=int, default=None, help="Độ đổ bóng")

    burn = subparsers.add_parser(
        "burn-sub",
        help="Burn ASS vào video bằng FFmpeg",
    )
    burn.add_argument("--video", required=True, help="Video đầu vào")
    burn.add_argument("--ass", required=True, help="File ASS")
    burn.add_argument("--output", required=True, help="Video đầu ra")
    burn.add_argument("--ffmpeg-path", default="", help="Đường dẫn ffmpeg")
    burn.add_argument("--fonts-dir", default="", help="Thư mục font cho libass")
    burn.add_argument("--video-codec", default="libx264", help="Codec video")
    burn.add_argument("--audio-codec", default="copy", help="Codec audio")
    burn.add_argument("--crf", type=int, default=18, help="CRF encode video")
    burn.add_argument("--preset", default="medium", help="Preset encode video")
    burn.add_argument(
        "--mask-mode",
        default="none",
        choices=["none", "box", "blur", "crop"],
        help="Chế độ che subtitle cũ",
    )
    burn.add_argument("--mask-rect", default="", help="Vùng che dạng x,y,w,h")
    burn.add_argument("--box-color", default="black@0.85", help="Màu box che subtitle")
    burn.add_argument("--blur-strength", type=int, default=12, help="Độ blur")

    pick = subparsers.add_parser(
        "pick-mask-rect",
        help="Mở frame video để khoanh vùng subtitle cũ",
    )
    pick.add_argument("--video", required=True, help="Video đầu vào")
    pick.add_argument("--timestamp", default="00:00:03", help="Thời điểm lấy frame")
    pick.add_argument("--output", default="mask_rect.json", help="File JSON tọa độ")
    pick.add_argument("--ffmpeg-path", default="", help="Đường dẫn ffmpeg")

    pipeline = subparsers.add_parser(
        "subtitle-pipeline",
        help="Chạy translate -> ASS -> optional mask -> burn",
    )
    pipeline.add_argument("--video", required=True, help="Video đầu vào")
    pipeline.add_argument("--srt", required=True, help="File SRT đầu vào")
    pipeline.add_argument("--output", default="", help="Video đầu ra")
    pipeline.add_argument("--output-dir", default="", help="Thư mục output trung gian")
    pipeline.add_argument("--source-lang", default="zh", help="Ngôn ngữ nguồn")
    pipeline.add_argument("--target-lang", default="vi", help="Ngôn ngữ đích")
    pipeline.add_argument("--translator", default="noop", help="Backend dịch")
    pipeline.add_argument("--batch-size", type=int, default=20, help="Số cue mỗi batch")
    pipeline.add_argument("--style-preset", default="douyin_vi", help="Style preset")
    pipeline.add_argument("--mask-mode", default="none", choices=["none", "box", "blur", "crop"])
    pipeline.add_argument("--mask-rect", default="", help="Vùng che dạng x,y,w,h")
    pipeline.add_argument("--ffmpeg-path", default="", help="Đường dẫn ffmpeg")
    pipeline.add_argument("--fonts-dir", default="", help="Thư mục font cho libass")
    pipeline.add_argument("--no-burn", action="store_true", help="Chỉ dịch và tạo ASS")


async def run_subtitle_subcommand(args: Any, _config: Any, display: Any) -> bool:
    command = getattr(args, "subtitle_command", None)
    if command == "translate-srt":
        _run_translate_srt(args, display)
        return True
    if command == "srt-to-ass":
        _run_srt_to_ass(args, _config, display)
        return True
    if command == "burn-sub":
        _run_burn_sub(args, display)
        return True
    if command == "pick-mask-rect":
        _run_pick_mask_rect(args, display)
        return True
    if command == "subtitle-pipeline":
        _run_subtitle_pipeline(args, _config, display)
        return True
    return False


def _run_translate_srt(args: Any, display: Any) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    cues = parse_srt(input_path)
    translator = create_translator(args.translator)
    translated = translate_cues(
        cues,
        translator,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        batch_size=args.batch_size,
        preserve_line_breaks=bool(args.preserve_line_breaks),
    )
    validate_same_timing(cues, translated)
    write_srt(output_path, translated)
    display.print_success(
        f"Đã dịch {len(translated)} cue, giữ nguyên timestamp: {output_path}"
    )


def _run_srt_to_ass(args: Any, config: Any, display: Any) -> None:
    overrides = {
        "font": args.font,
        "font_size": args.font_size,
        "alignment": args.alignment,
        "margin_v": args.margin_v,
        "outline": args.outline,
        "shadow": args.shadow,
    }
    style = AssStyle.from_config(
        config.get("subtitle", {}) if hasattr(config, "get") else {},
        preset_name=args.style_preset,
        overrides=overrides,
    )
    convert_srt_to_ass(Path(args.input), Path(args.output), style)
    display.print_success(f"Đã convert SRT sang ASS: {args.output}")


def _run_burn_sub(args: Any, display: Any) -> None:
    rect = MaskRect.parse(args.mask_rect) if args.mask_rect else None
    video_filter = build_masked_subtitle_filter(
        ass_path=Path(args.ass),
        fonts_dir=args.fonts_dir,
        mode=args.mask_mode,
        rect=rect,
        box_color=args.box_color,
        blur_strength=args.blur_strength,
    )
    burn_ass(
        video_path=Path(args.video),
        ass_path=Path(args.ass),
        output_path=Path(args.output),
        ffmpeg_path=args.ffmpeg_path,
        fonts_dir=args.fonts_dir,
        video_codec=args.video_codec,
        audio_codec=args.audio_codec,
        crf=args.crf,
        preset=args.preset,
        video_filter=video_filter,
    )
    display.print_success(f"Đã burn subtitle vào video: {args.output}")


def _run_pick_mask_rect(args: Any, display: Any) -> None:
    rect = pick_mask_rect(
        video_path=Path(args.video),
        timestamp=args.timestamp,
        output_json=Path(args.output),
        ffmpeg_path=args.ffmpeg_path,
    )
    display.print_success(
        f"Selected rect: {rect.to_cli_value()}\n"
        f"Use: --mask-mode blur --mask-rect {rect.to_cli_value()}\n"
        f"Saved: {args.output}"
    )


def _run_subtitle_pipeline(args: Any, config: Any, display: Any) -> None:
    video_path = Path(args.video)
    input_srt = Path(args.srt)
    output_dir = Path(args.output_dir) if args.output_dir else input_srt.parent
    rect = MaskRect.parse(args.mask_rect) if args.mask_rect else None

    def _progress(stage: str, current: int, total: int, message: str) -> None:
        display.print_info(f"[{current}/{total}] {stage}: {message}")

    result = SubtitlePipeline(progress_callback=_progress).run(
        video_path=video_path,
        input_srt_path=input_srt,
        output_video_path=Path(args.output) if args.output else None,
        output_dir=output_dir,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        translator_name=args.translator,
        batch_size=args.batch_size,
        style_preset=args.style_preset,
        subtitle_config=config.get("subtitle", {}) if hasattr(config, "get") else {},
        mask_mode=args.mask_mode,
        mask_rect=rect,
        ffmpeg_path=args.ffmpeg_path,
        fonts_dir=args.fonts_dir,
        burn=not args.no_burn,
    )
    if result.status == "success":
        display.print_success(f"Subtitle pipeline hoàn tất: {result.outputs}")
    else:
        display.print_error(result.error or "Subtitle pipeline failed")
