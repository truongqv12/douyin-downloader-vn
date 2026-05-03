from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from .ass_converter import convert_srt_to_ass
from .burner import burn_ass
from .mask import build_masked_subtitle_filter
from .models import MaskRect
from .result import PipelineResult
from .srt_parser import parse_srt, validate_same_timing, write_srt
from .style import AssStyle
from .translator import create_translator, translate_cues

ProgressCallback = Callable[[str, int, int, str], None]


class SubtitlePipeline:
    def __init__(self, progress_callback: Optional[ProgressCallback] = None):
        self.progress_callback = progress_callback

    def run(
        self,
        *,
        video_path: Path,
        input_srt_path: Path,
        output_video_path: Optional[Path],
        output_dir: Path,
        source_lang: str = "zh",
        target_lang: str = "vi",
        translator_name: str = "noop",
        batch_size: int = 20,
        style: Optional[AssStyle] = None,
        style_preset: str = "douyin_vi",
        subtitle_config: Optional[Dict[str, object]] = None,
        mask_mode: str = "none",
        mask_rect: Optional[MaskRect] = None,
        ffmpeg_path: str = "",
        fonts_dir: str = "",
        burn: bool = True,
    ) -> PipelineResult:
        result = PipelineResult(status="running", stage="parse")
        output_dir.mkdir(parents=True, exist_ok=True)

        translated_srt = output_dir / f"{input_srt_path.stem}.{target_lang}.srt"
        ass_path = output_dir / f"{input_srt_path.stem}.{target_lang}.ass"
        final_video = output_video_path or output_dir / f"{video_path.stem}.{target_lang}.mp4"

        try:
            result.stage = "parse"
            self._progress("parse", 1, 5, "Parsing SRT")
            cues = parse_srt(input_srt_path)

            result.stage = "translate"
            self._progress("translate", 2, 5, "Translating subtitle text")
            translator = create_translator(translator_name)
            translated = translate_cues(
                cues,
                translator,
                source_lang=source_lang,
                target_lang=target_lang,
                batch_size=batch_size,
            )
            validate_same_timing(cues, translated)
            write_srt(translated_srt, translated)
            result.outputs["translated_srt"] = str(translated_srt)

            result.stage = "convert_ass"
            self._progress("convert_ass", 3, 5, "Converting SRT to ASS")
            style_obj = style or AssStyle.from_config(
                subtitle_config or {},
                preset_name=style_preset,
            )
            convert_srt_to_ass(translated_srt, ass_path, style_obj)
            result.outputs["ass"] = str(ass_path)

            if burn:
                result.stage = "burn"
                self._progress("burn", 4, 5, "Burning ASS into video")
                video_filter = build_masked_subtitle_filter(
                    ass_path=ass_path,
                    fonts_dir=fonts_dir,
                    mode=mask_mode,
                    rect=mask_rect,
                )
                burn_ass(
                    video_path=video_path,
                    ass_path=ass_path,
                    output_path=final_video,
                    ffmpeg_path=ffmpeg_path,
                    fonts_dir=fonts_dir,
                    video_filter=video_filter,
                )
                result.outputs["video"] = str(final_video)

            self._progress("done", 5, 5, "Subtitle pipeline completed")
            result.status = "success"
            result.stage = "done"
            return result
        except Exception as exc:
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"
            return result

    def _progress(self, stage: str, current: int, total: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(stage, current, total, message)
