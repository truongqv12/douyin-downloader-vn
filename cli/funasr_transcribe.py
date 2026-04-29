#!/usr/bin/env python3
"""
funasr_transcribe.py — Paraformer/FunASR 批量中文转录 + SRT

目标:
  - 更偏向普通话中文识别准确率
  - 支持长视频: ffmpeg -> 16k mono wav -> FunASR VAD -> Paraformer-zh -> punctuation -> TXT/SRT
  - CLI 结构尽量贴近原 whisper_transcribe.py

安装:
  pip install -U funasr modelscope rich
  # 可选繁转简:
  pip install OpenCC
  # ffmpeg: conda install -c conda-forge ffmpeg 或把 ffmpeg.exe 放到同目录

用法:
  python funasr_transcribe.py
  python funasr_transcribe.py -d ./Downloaded --srt
  python funasr_transcribe.py -f video.mp4 --srt
  python funasr_transcribe.py -d ./Downloaded --srt --skip-existing --sc
  python funasr_transcribe.py -d ./Downloaded --srt --device cpu --batch-size-s 60
  python funasr_transcribe.py -d ./Downloaded --srt --hotword hotwords.txt

说明:
  - 默认模型: paraformer-zh + fsmn-vad + ct-punc-c
  - 默认启用 sentence_timestamp=True，用于尽量生成句级 SRT
  - 如果 FunASR 没返回句级 timestamp，会 fallback 成按文本长度均分时间；这种 SRT 只适合粗略检查
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()

THEME = {
    "accent": "bright_green",
    "banner": "bold bright_green",
    "info": "dodger_blue1",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "dim": "dim white",
    "file": "bright_cyan",
    "model": "orchid",
}


class TranscribeDisplay:
    def __init__(self):
        self.console = console
        self._progress_ctx: Optional[Progress] = None
        self._progress: Optional[Progress] = None
        self._overall_id: Optional[int] = None
        self._file_id: Optional[int] = None
        self._file_index = 0
        self._file_total = 0
        self._stats = {"success": 0, "failed": 0, "skipped": 0}

    def show_banner(self):
        banner = Text()
        banner.append("  🎙  FunASR 中文转录工具\n", style="bold bright_green")
        banner.append("  ── Video → Text/SRT via Paraformer-zh ──", style="dim bright_green")
        panel = Panel(banner, border_style="bright_green", expand=False, padding=(0, 2))
        self.console.print(panel)
        self.console.print()

    def start_session(self, total: int):
        self._file_total = total
        self._file_index = 0
        self._stats = {"success": 0, "failed": 0, "skipped": 0}
        self._progress_ctx = Progress(
            SpinnerColumn(style="bright_green"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30, complete_style="bright_green", finished_style="green"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TextColumn("[dim]{task.fields[detail]}"),
            console=self.console,
            transient=True,
            refresh_per_second=6,
        )
        self._progress = self._progress_ctx.__enter__()
        self._overall_id = self._progress.add_task(
            "[bright_green]总体进度[/]",
            total=max(total, 1),
            completed=0,
            detail=f"共 {total} 个视频",
        )

    def stop_session(self):
        if self._file_id is not None and self._progress:
            self._progress.remove_task(self._file_id)
            self._file_id = None
        if self._progress_ctx is not None:
            self._progress_ctx.__exit__(None, None, None)
        self._progress_ctx = None
        self._progress = None
        self._overall_id = None

    def start_file(self, index: int, name: str):
        self._file_index = index
        if self._file_id is not None and self._progress:
            self._progress.remove_task(self._file_id)
        if not self._progress:
            return
        self._file_id = self._progress.add_task(
            self._file_desc("提取音频"),
            total=4,
            completed=0,
            detail=self._shorten(name, 50),
        )

    def advance_file(self, step: str, detail: str = ""):
        if not self._progress or self._file_id is None:
            return
        self._progress.advance(self._file_id, 1)
        self._progress.update(self._file_id, description=self._file_desc(step), detail=detail)

    def complete_file(self, status: str, detail: str = ""):
        if status in self._stats:
            self._stats[status] += 1
        if self._progress:
            if self._file_id is not None:
                title = "完成" if status == "success" else "跳过" if status == "skipped" else "失败"
                self._progress.update(self._file_id, completed=4, description=self._file_desc(title), detail=detail)
                self._progress.remove_task(self._file_id)
                self._file_id = None
            if self._overall_id is not None:
                self._progress.advance(self._overall_id, 1)
                self._progress.update(
                    self._overall_id,
                    detail=f"✓{self._stats['success']}  ✗{self._stats['failed']}  ⊘{self._stats['skipped']}",
                )

    def show_summary(self):
        table = Table(title="Transcription Summary", show_header=True, header_style=f"bold {THEME['accent']}", border_style=THEME["accent"])
        table.add_column("Metric", style=THEME["info"])
        table.add_column("Count", justify="right", style=THEME["success"])
        total = self._stats["success"] + self._stats["failed"] + self._stats["skipped"]
        table.add_row("Total", str(total))
        table.add_row("Success", str(self._stats["success"]))
        table.add_row("Failed", str(self._stats["failed"]))
        table.add_row("Skipped", str(self._stats["skipped"]))
        if total > 0:
            table.add_row("Success Rate", f"{self._stats['success'] / total * 100:.1f}%")
        self.console.print()
        self.console.print(table)

    def info(self, msg: str):
        self._out().print(f"[{THEME['info']}]ℹ[/] {msg}")

    def success(self, msg: str):
        self._out().print(f"[{THEME['success']}]✓[/] {msg}")

    def warning(self, msg: str):
        self._out().print(f"[{THEME['warning']}]⚠[/] {msg}")

    def error(self, msg: str):
        self._out().print(f"[{THEME['error']}]✗[/] {msg}")

    def dep_ok(self, name: str, detail: str = ""):
        self._out().print(f"  [{THEME['success']}]✓[/] {name}  [{THEME['dim']}]{detail}[/]")

    def dep_fail(self, name: str, hint: str):
        self._out().print(f"  [{THEME['error']}]✗[/] {name}  [{THEME['dim']}]{hint}[/]")

    def _file_desc(self, step: str) -> str:
        return f"[{THEME['accent']}]{self._file_index}/{self._file_total}[/] · {step}"

    def _out(self) -> Console:
        return self._progress.console if self._progress else self.console

    @staticmethod
    def _shorten(text: str, max_len: int = 50) -> str:
        t = (text or "").strip()
        return t if len(t) <= max_len else f"{t[:max_len - 3]}..."


display = TranscribeDisplay()


def find_ffmpeg() -> Optional[str]:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path(__file__).parent / "ffmpeg.exe"
    if local.exists():
        return str(local)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def find_ffprobe(ffmpeg_path: str) -> Optional[str]:
    p = shutil.which("ffprobe")
    if p:
        return p
    ffmpeg = Path(ffmpeg_path)
    candidate = ffmpeg.with_name("ffprobe.exe" if ffmpeg.name.lower().endswith(".exe") else "ffprobe")
    if candidate.exists():
        return str(candidate)
    return None


def extract_audio(video_path: Path, audio_path: Path, ffmpeg_path: str) -> bool:
    cmd = [
        ffmpeg_path, "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(audio_path), "-y", "-loglevel", "error",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"  [{THEME['error']}]ffmpeg错误: {result.stderr.strip()}[/]")
    return result.returncode == 0 and audio_path.exists()


def get_wav_duration_seconds(wav_path: Path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 16000
            return float(frames) / float(rate)
    except Exception:
        return 0.0


def _format_srt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds or 0.0))
    h, r = divmod(seconds, 3600)
    m, r = divmod(r, 60)
    s = int(r)
    ms = int(round((r - s) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{int(h):02d}:{int(m):02d}:{s:02d},{ms:03d}"


def _safe_stem(stem: str) -> str:
    stem = stem.replace("\n", " ").replace("\r", " ")
    stem = re.sub(r'[<>:"/\\|?*#]', "_", stem)
    stem = re.sub(r"[\s_]+", "_", stem)
    stem = stem.strip("_ ")
    return stem[:150] if len(stem) > 150 else stem


def resolve_output_dir(video_path: Path, output_dir: Optional[str]) -> Path:
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = None
        try:
            candidate = video_path.parent
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".funasr_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            out_dir = candidate
        except Exception:
            out_dir = None
        if out_dir is None:
            out_dir = Path("./transcripts")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def copy_to_temp(video_path: Path, tmp_video: Path) -> bool:
    try:
        shutil.copy2(str(video_path), str(tmp_video))
        return True
    except Exception as e:
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            ctypes.windll.kernel32.GetShortPathNameW(str(video_path), buf, 1024)
            short_path = buf.value
            if short_path:
                shutil.copy2(short_path, str(tmp_video))
                return True
        except Exception:
            pass
        console.print(f"  [{THEME['error']}]无法访问视频文件: {e}[/]")
        return False


def _cv(text: str, converter: Any) -> str:
    return converter.convert(text) if converter and text else text


def clean_text(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"<\|[^>]+?\|>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _first(d: Dict[str, Any], names: Sequence[str], default: Any = None) -> Any:
    for name in names:
        if name in d and d[name] is not None:
            return d[name]
    return default


def _time_to_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    # FunASR sentence timestamps are usually in milliseconds.
    if abs(v) > 100.0:
        return v / 1000.0
    return v


def _is_valid_time_pair(start: Optional[float], end: Optional[float]) -> bool:
    return start is not None and end is not None and end > start and end - start < 60 * 60


def split_text_for_srt(text: str, max_chars: int = 24) -> List[str]:
    text = clean_text(text)
    if not text:
        return []
    out: List[str] = []
    buf = ""
    hard_marks = set("。！？!?；;")
    soft_marks = set("，,、")
    for ch in text:
        buf += ch
        if (ch in hard_marks and len(buf) >= 6) or len(buf) >= max_chars:
            out.append(buf.strip())
            buf = ""
        elif ch in soft_marks and len(buf) >= max_chars * 0.75:
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return [x for x in out if x]


def split_cue(start: float, end: float, text: str, max_chars: int) -> List[Dict[str, Any]]:
    chunks = split_text_for_srt(text, max_chars=max_chars)
    if not chunks:
        return []
    if len(chunks) == 1:
        return [{"start": start, "end": end, "text": chunks[0]}]
    total_chars = sum(max(1, len(c)) for c in chunks)
    duration = max(0.2, end - start)
    cues = []
    cur = start
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            nxt = end
        else:
            portion = max(1, len(chunk)) / total_chars
            nxt = min(end, cur + duration * portion)
        if nxt <= cur:
            nxt = cur + 0.2
        cues.append({"start": cur, "end": nxt, "text": chunk})
        cur = nxt
    return cues


def _iter_result_items(result: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(result, dict):
        yield result
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                yield item


def extract_cues_from_funasr(result: Any, duration: float, max_chars: int) -> Tuple[List[Dict[str, Any]], str, bool]:
    """
    Return: cues, full_text, used_real_timestamps
    """
    cues: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    used_real_ts = False

    for item in _iter_result_items(result):
        item_text = clean_text(item.get("text", ""))
        if item_text:
            text_parts.append(item_text)

        # Preferred: sentence-level timestamps.
        for key in ("sentence_info", "sentences", "segments"):
            val = item.get(key)
            if not isinstance(val, list):
                continue
            for sent in val:
                if not isinstance(sent, dict):
                    continue
                t = clean_text(_first(sent, ("text", "sentence", "value"), ""))
                start = _time_to_seconds(_first(sent, ("start", "start_time", "begin", "begin_time"), None))
                end = _time_to_seconds(_first(sent, ("end", "end_time", "finish", "finish_time"), None))
                if t and _is_valid_time_pair(start, end):
                    cues.extend(split_cue(float(start), float(end), t, max_chars=max_chars))
                    used_real_ts = True

        # Secondary: item itself is a timed segment.
        start = _time_to_seconds(_first(item, ("start", "start_time", "begin", "begin_time"), None))
        end = _time_to_seconds(_first(item, ("end", "end_time", "finish", "finish_time"), None))
        if item_text and _is_valid_time_pair(start, end):
            cues.extend(split_cue(float(start), float(end), item_text, max_chars=max_chars))
            used_real_ts = True

    full_text = "\n".join(text_parts).strip()

    if cues:
        cues.sort(key=lambda x: (x["start"], x["end"]))
        # Drop overlaps caused by duplicate sentence_info + item-level segments.
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for c in cues:
            key = (round(c["start"], 2), round(c["end"], 2), c["text"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
        return deduped, full_text, used_real_ts

    # Fallback: no timestamps. Split whole text across the audio duration.
    if full_text and duration > 0:
        return split_cue(0.0, duration, full_text, max_chars=max_chars), full_text, False
    if full_text:
        return [{"start": 0.0, "end": max(2.0, len(full_text) / 6.0), "text": full_text}], full_text, False
    return [], full_text, False


def write_txt(path: Path, text: str) -> None:
    path.write_text((text or "").strip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_srt(path: Path, cues: List[Dict[str, Any]], converter: Any = None) -> None:
    lines = []
    last_end = 0.0
    for i, cue in enumerate(cues, 1):
        start = max(0.0, float(cue["start"]))
        end = max(start + 0.2, float(cue["end"]))
        # Avoid visually bad overlap.
        if start < last_end:
            start = last_end
            end = max(end, start + 0.2)
        last_end = end
        text = _cv(clean_text(cue["text"]), converter)
        if not text:
            continue
        lines.append(f"{i}\n{_format_srt_time(start)} --> {_format_srt_time(end)}\n{text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def find_videos(directory: str, skip_existing: bool = False, output_dir: Optional[str] = None) -> List[Path]:
    directory_path = Path(directory)
    if not directory_path.exists():
        display.error(f"目录不存在: {directory_path}")
        return []
    videos: List[Path] = []
    for ext in ("*.mp4", "*.mov", "*.mkv", "*.webm", "*.m4a", "*.mp3", "*.wav", "*.flac", "*.aac"):
        videos.extend(directory_path.rglob(ext))
    videos = sorted(set(videos))

    if skip_existing:
        filtered = []
        for v in videos:
            safe = _safe_stem(v.stem)
            dirs_to_check = [v.parent]
            if output_dir:
                dirs_to_check.append(Path(output_dir))
            dirs_to_check.append(Path("./transcripts"))
            found = any((d / f"{safe}.transcript.txt").exists() for d in dirs_to_check)
            if found:
                display.info(f"跳过 {safe[:50]}... (已有 transcript)")
            else:
                filtered.append(v)
        videos = filtered
    return videos


def load_converter(enabled: bool) -> Any:
    if not enabled:
        return None
    try:
        from opencc import OpenCC
        return OpenCC("t2s")
    except ImportError:
        display.dep_fail("OpenCC", "pip install OpenCC")
        sys.exit(1)


def maybe_set_torch_threads(num_threads: int) -> None:
    if num_threads <= 0:
        return
    try:
        import torch
        torch.set_num_threads(num_threads)
        torch.set_num_interop_threads(max(1, min(4, num_threads)))
    except Exception:
        pass


def transcribe_file(
    video_path: Path,
    model: Any,
    ffmpeg_path: str,
    output_formats: set[str],
    converter: Any,
    output_dir: Optional[str],
    args: argparse.Namespace,
) -> bool:
    video_path = Path(video_path)
    stem = _safe_stem(video_path.stem)
    out_dir = resolve_output_dir(video_path, output_dir)
    txt_path = out_dir / f"{stem}.transcript.txt"
    srt_path = out_dir / f"{stem}.transcript.srt"
    json_path = out_dir / f"{stem}.transcript.funasr.json"

    tmpdir = Path(tempfile.mkdtemp(prefix="funasr_"))
    try:
        tmp_video = tmpdir / ("input" + video_path.suffix.lower())
        if not copy_to_temp(video_path, tmp_video):
            display.advance_file("失败", "路径不可达")
            return False

        audio_path = tmpdir / "audio.wav"
        if not extract_audio(tmp_video, audio_path, ffmpeg_path):
            display.advance_file("失败", "音频提取失败")
            return False

        duration = get_wav_duration_seconds(audio_path)
        audio_mb = audio_path.stat().st_size / 1024 / 1024
        display.advance_file("识别中", f"音频 {audio_mb:.1f}MB / {duration:.1f}s")

        gen_kwargs: Dict[str, Any] = {
            "input": str(audio_path),
            "batch_size_s": args.batch_size_s,
            "sentence_timestamp": not args.no_sentence_timestamp,
        }
        if args.hotword:
            hotword_path = Path(args.hotword)
            if hotword_path.exists():
                gen_kwargs["hotword"] = hotword_path.read_text(encoding="utf-8")
            else:
                gen_kwargs["hotword"] = args.hotword

        result = model.generate(**gen_kwargs)
        cues, full_text, used_real_ts = extract_cues_from_funasr(result, duration=duration, max_chars=args.max_chars)

        full_text = _cv(full_text, converter)
        if not full_text and cues:
            full_text = "\n".join(_cv(c["text"], converter) for c in cues if c.get("text"))

        if not full_text.strip():
            display.advance_file("无内容", "未检测到语音")
            return False

        tag = "句级时间戳" if used_real_ts else "fallback时间"
        display.advance_file("保存", f"{len(cues)}段 · {tag}")

        saved = []
        if "txt" in output_formats:
            write_txt(txt_path, full_text)
            saved.append(txt_path.name)
        if "srt" in output_formats:
            write_srt(srt_path, cues, converter=converter)
            saved.append(srt_path.name)
        if args.json:
            payload = {
                "source": str(video_path),
                "duration": duration,
                "used_real_timestamps": used_real_ts,
                "result": result,
            }
            write_json(json_path, payload)
            saved.append(json_path.name)

        display.advance_file("完成", " + ".join(saved))
        return True

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def build_model(args: argparse.Namespace) -> Any:
    from funasr import AutoModel

    kwargs: Dict[str, Any] = {
        "model": args.model,
        "device": args.device,
    }
    if args.model_revision:
        kwargs["model_revision"] = args.model_revision
    if args.disable_update:
        kwargs["disable_update"] = True
    if args.hub:
        kwargs["hub"] = args.hub

    if not args.no_vad:
        kwargs["vad_model"] = args.vad_model
        if args.vad_model_revision:
            kwargs["vad_model_revision"] = args.vad_model_revision
        kwargs["vad_kwargs"] = {"max_single_segment_time": args.max_single_segment_ms}

    if not args.no_punc:
        kwargs["punc_model"] = args.punc_model
        if args.punc_model_revision:
            kwargs["punc_model_revision"] = args.punc_model_revision

    return AutoModel(**kwargs)


def main():
    parser = argparse.ArgumentParser(
        description="FunASR Paraformer 中文批量转录工具 — 视频/音频 → TXT/SRT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python funasr_transcribe.py -d ./Downloaded --srt\n"
            "  python funasr_transcribe.py -f video.mp4 --srt --device cpu\n"
            "  python funasr_transcribe.py -d ./Downloaded --srt --batch-size-s 60 --skip-existing\n"
            "  python funasr_transcribe.py -d ./Downloaded --srt --hotword hotwords.txt"
        ),
    )
    parser.add_argument("-d", "--dir", default="./Downloaded", help="视频/音频目录 (默认 ./Downloaded/)")
    parser.add_argument("-f", "--file", help="单个视频/音频文件")
    parser.add_argument("-o", "--output", default=None, help="转录文件输出目录")
    parser.add_argument("--srt", action="store_true", help="同时输出 SRT 字幕")
    parser.add_argument("--json", action="store_true", help="同时保存 FunASR 原始 JSON，便于排查 timestamp")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已有 transcript 的视频")
    parser.add_argument("--sc", action="store_true", help="繁体转简体 (需 pip install OpenCC)")

    parser.add_argument("--model", default="paraformer-zh", help="FunASR ASR 模型，默认 paraformer-zh")
    parser.add_argument("--model-revision", default="v2.0.4", help="ASR model revision；空字符串则不指定")
    parser.add_argument("--vad-model", default="fsmn-vad", help="VAD 模型")
    parser.add_argument("--vad-model-revision", default="v2.0.4", help="VAD model revision；空字符串则不指定")
    parser.add_argument("--punc-model", default="ct-punc-c", help="标点模型")
    parser.add_argument("--punc-model-revision", default="v2.0.4", help="Punc model revision；空字符串则不指定")
    parser.add_argument("--no-vad", action="store_true", help="禁用 VAD，不建议处理长视频时使用")
    parser.add_argument("--no-punc", action="store_true", help="禁用标点模型")
    parser.add_argument("--no-sentence-timestamp", action="store_true", help="禁用 sentence_timestamp")
    parser.add_argument("--max-single-segment-ms", type=int, default=15000, help="VAD 单段最长毫秒数，机器弱建议 10000~20000")
    parser.add_argument("--batch-size-s", type=int, default=60, help="动态 batch 秒数；CPU 弱建议 30~60")
    parser.add_argument("--max-chars", type=int, default=24, help="SRT 单条最大字数")
    parser.add_argument("--hotword", default="", help="热词字符串或 hotwords.txt 路径")
    parser.add_argument("--device", default="cpu", help='cpu / cuda:0；默认 cpu')
    parser.add_argument("--num-threads", type=int, default=0, help="限制 PyTorch CPU 线程数，0 表示不设置")
    parser.add_argument("--hub", default="", help='可选: "ms" / "hf" 等；空则用默认')
    parser.add_argument("--disable-update", action="store_true", help="禁用模型更新检查")

    args = parser.parse_args()
    if args.model_revision == "":
        args.model_revision = None
    if args.vad_model_revision == "":
        args.vad_model_revision = None
    if args.punc_model_revision == "":
        args.punc_model_revision = None

    display.show_banner()
    console.print(f"  [{THEME['dim']}]检查依赖...[/]")

    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        display.dep_fail("ffmpeg", "conda install -c conda-forge ffmpeg 或放 ffmpeg.exe 到同目录")
        sys.exit(1)
    display.dep_ok("ffmpeg", ffmpeg_path)

    try:
        import funasr  # noqa: F401
    except ImportError:
        display.dep_fail("funasr", "pip install -U funasr modelscope")
        sys.exit(1)
    display.dep_ok("funasr", "已安装")

    converter = load_converter(args.sc)
    if converter:
        display.dep_ok("OpenCC", "繁体→简体")

    maybe_set_torch_threads(args.num_threads)
    console.print()

    if args.file:
        videos = [Path(args.file)]
        if not videos[0].exists():
            display.error(f"文件不存在: {args.file}")
            sys.exit(1)
    else:
        videos = find_videos(args.dir, skip_existing=args.skip_existing, output_dir=args.output)

    if not videos:
        display.warning("没有找到需要处理的视频/音频文件")
        return

    display.info(f"找到 {len(videos)} 个文件")
    display.info(f"加载 FunASR 模型: [{THEME['model']}]{args.model}[/] device={args.device}")
    model = build_model(args)
    display.success(f"模型 [{THEME['model']}]{args.model}[/] 加载完成")
    console.print()

    output_formats = {"txt"}
    if args.srt:
        output_formats.add("srt")

    display.start_session(len(videos))
    try:
        for i, video in enumerate(videos, 1):
            display.start_file(i, video.name)
            try:
                ok = transcribe_file(video, model, ffmpeg_path, output_formats, converter, args.output, args)
                display.complete_file("success" if ok else "failed", video.name if ok else "识别失败")
            except KeyboardInterrupt:
                display.complete_file("failed", "用户中断")
                raise
            except Exception as e:
                display.complete_file("failed", str(e)[:60])
                console.print(f"  [{THEME['error']}]错误详情: {e}[/]")
                import traceback
                console.print(f"[{THEME['dim']}]{traceback.format_exc()}[/]")
    except KeyboardInterrupt:
        display.warning("用户中断")
    finally:
        display.stop_session()

    display.show_summary()


if __name__ == "__main__":
    main()
