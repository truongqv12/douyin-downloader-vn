from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .models import MaskRect
from .pipeline import SubtitlePipeline
from .result import PipelineResult

DEFAULT_VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
DEFAULT_SRT_SUFFIXES = (".transcript.srt", ".srt")

BatchProgressCallback = Callable[[str, int, int, str], None]


@dataclass(frozen=True)
class SubtitleBatchItem:
    video_path: Path
    srt_path: Optional[Path] = None
    output_dir: Optional[Path] = None
    output_video_path: Optional[Path] = None
    skip_reason: str = ""


@dataclass
class SubtitleBatchItemResult:
    video_path: str
    srt_path: str = ""
    status: str = "pending"
    outputs: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class SubtitleBatchSummary:
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[SubtitleBatchItemResult] = field(default_factory=list)

    def add_result(self, result: SubtitleBatchItemResult) -> None:
        self.results.append(result)
        self.total += 1
        if result.status == "success":
            self.success += 1
        elif result.status == "skipped":
            self.skipped += 1
        else:
            self.failed += 1

    def to_dict(self) -> Dict[str, object]:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [
                {
                    "video_path": result.video_path,
                    "srt_path": result.srt_path,
                    "status": result.status,
                    "outputs": dict(result.outputs),
                    "error": result.error,
                }
                for result in self.results
            ],
        }


def parse_csv_values(raw: str, defaults: Sequence[str]) -> List[str]:
    values = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    return values or list(defaults)


def discover_video_paths(
    *,
    directory: Path,
    file_path: Optional[Path] = None,
    video_extensions: Sequence[str] = DEFAULT_VIDEO_EXTENSIONS,
) -> List[Path]:
    if file_path:
        return [file_path]
    if not directory.exists():
        return []
    normalized_exts = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in video_extensions}
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in normalized_exts
    )


def find_matching_srt(
    video_path: Path,
    *,
    srt_suffixes: Sequence[str] = DEFAULT_SRT_SUFFIXES,
    srt_dir: Optional[Path] = None,
) -> Optional[Path]:
    search_dir = srt_dir or video_path.parent
    for suffix in srt_suffixes:
        candidate = search_dir / f"{video_path.stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def output_paths_for_item(
    *,
    video_path: Path,
    base_dir: Path,
    output_dir: Path,
    target_lang: str,
    preserve_tree: bool = True,
) -> Tuple[Path, Path]:
    if preserve_tree:
        try:
            relative_parent = video_path.parent.relative_to(base_dir)
        except ValueError:
            relative_parent = Path()
        item_output_dir = output_dir / relative_parent / video_path.stem
    else:
        item_output_dir = output_dir / video_path.stem
    output_video_path = item_output_dir / f"{video_path.stem}.{target_lang}.mp4"
    return item_output_dir, output_video_path


def build_batch_items(
    *,
    directory: Path,
    output_dir: Path,
    target_lang: str,
    file_path: Optional[Path] = None,
    video_extensions: Sequence[str] = DEFAULT_VIDEO_EXTENSIONS,
    srt_suffixes: Sequence[str] = DEFAULT_SRT_SUFFIXES,
    srt_dir: Optional[Path] = None,
    skip_existing: bool = False,
    preserve_tree: bool = True,
) -> List[SubtitleBatchItem]:
    items: List[SubtitleBatchItem] = []
    for video_path in discover_video_paths(
        directory=directory,
        file_path=file_path,
        video_extensions=video_extensions,
    ):
        item_output_dir, output_video_path = output_paths_for_item(
            video_path=video_path,
            base_dir=directory,
            output_dir=output_dir,
            target_lang=target_lang,
            preserve_tree=preserve_tree,
        )
        # Skip-existing checks the final video because intermediate SRT/ASS can be reused.
        if skip_existing and output_video_path.exists():
            items.append(
                SubtitleBatchItem(
                    video_path=video_path,
                    output_dir=item_output_dir,
                    output_video_path=output_video_path,
                    skip_reason="output video already exists",
                )
            )
            continue
        srt_path = find_matching_srt(video_path, srt_suffixes=srt_suffixes, srt_dir=srt_dir)
        if srt_path is None:
            items.append(
                SubtitleBatchItem(
                    video_path=video_path,
                    output_dir=item_output_dir,
                    output_video_path=output_video_path,
                    skip_reason="matching srt not found",
                )
            )
            continue
        items.append(
            SubtitleBatchItem(
                video_path=video_path,
                srt_path=srt_path,
                output_dir=item_output_dir,
                output_video_path=output_video_path,
            )
        )
    return items


def run_subtitle_batch(
    *,
    directory: Path,
    output_dir: Path,
    source_lang: str = "zh",
    target_lang: str = "vi",
    translator_name: str = "noop",
    batch_size: int = 20,
    style_preset: str = "douyin_vi",
    subtitle_config: Optional[Dict[str, object]] = None,
    mask_mode: str = "none",
    mask_rect: Optional[MaskRect] = None,
    ffmpeg_path: str = "",
    fonts_dir: str = "",
    burn: bool = True,
    file_path: Optional[Path] = None,
    video_extensions: Sequence[str] = DEFAULT_VIDEO_EXTENSIONS,
    srt_suffixes: Sequence[str] = DEFAULT_SRT_SUFFIXES,
    srt_dir: Optional[Path] = None,
    skip_existing: bool = False,
    preserve_tree: bool = True,
    progress_callback: Optional[BatchProgressCallback] = None,
) -> SubtitleBatchSummary:
    items = build_batch_items(
        directory=directory,
        output_dir=output_dir,
        target_lang=target_lang,
        file_path=file_path,
        video_extensions=video_extensions,
        srt_suffixes=srt_suffixes,
        srt_dir=srt_dir,
        skip_existing=skip_existing,
        preserve_tree=preserve_tree,
    )
    summary = SubtitleBatchSummary()
    total = len(items)
    for index, item in enumerate(items, 1):
        if item.skip_reason:
            _progress(progress_callback, "skip", index, total, f"{item.video_path.name}: {item.skip_reason}")
            summary.add_result(
                SubtitleBatchItemResult(
                    video_path=str(item.video_path),
                    status="skipped",
                    error=item.skip_reason,
                )
            )
            continue
        _progress(progress_callback, "start", index, total, f"Processing {item.video_path.name}")
        result = SubtitlePipeline(
            progress_callback=_make_item_progress(progress_callback, index, total, item.video_path.name)
        ).run(
            video_path=item.video_path,
            input_srt_path=item.srt_path or Path(),
            output_video_path=item.output_video_path if burn else None,
            output_dir=item.output_dir or output_dir,
            source_lang=source_lang,
            target_lang=target_lang,
            translator_name=translator_name,
            batch_size=batch_size,
            style_preset=style_preset,
            subtitle_config=subtitle_config or {},
            mask_mode=mask_mode,
            mask_rect=mask_rect,
            ffmpeg_path=ffmpeg_path,
            fonts_dir=fonts_dir,
            burn=burn,
        )
        summary.add_result(_item_result_from_pipeline(item, result))
    return summary


def _make_item_progress(
    progress_callback: Optional[BatchProgressCallback],
    index: int,
    total: int,
    video_name: str,
) -> Optional[BatchProgressCallback]:
    if progress_callback is None:
        return None

    def _progress(stage: str, _current: int, _total: int, message: str) -> None:
        progress_callback(stage, index, total, f"{video_name}: {message}")

    return _progress


def _item_result_from_pipeline(
    item: SubtitleBatchItem,
    result: PipelineResult,
) -> SubtitleBatchItemResult:
    return SubtitleBatchItemResult(
        video_path=str(item.video_path),
        srt_path=str(item.srt_path or ""),
        status=result.status,
        outputs=dict(result.outputs),
        error=result.error,
    )


def _progress(
    progress_callback: Optional[BatchProgressCallback],
    stage: str,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress_callback:
        progress_callback(stage, current, total, message)
