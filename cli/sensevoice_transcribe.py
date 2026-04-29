#!/usr/bin/env python3
"""
sensevoice_transcribe.py — SenseVoiceSmall ONNX/sherpa-onnx 批量中文转录 + SRT

目标:
  - 机器弱 / CPU-only 时，比 PyTorch/FunASR 轻
  - 使用 sherpa-onnx + SenseVoiceSmall + Silero VAD
  - VAD 段时间直接用于 SRT cue，适合做字幕初稿
  - CLI 结构尽量贴近原 whisper_transcribe.py

安装:
  pip install -U sherpa-onnx numpy rich
  # 可选繁转简:
  pip install OpenCC
  # ffmpeg: conda install -c conda-forge ffmpeg 或把 ffmpeg.exe 放到同目录

模型准备示例:
  # 下载 silero_vad.onnx
  wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx

  # 下载 sherpa-onnx SenseVoice 模型包后解压，里面应有:
  #   model.onnx 或 model.int8.onnx
  #   tokens.txt

用法:
  python sensevoice_transcribe.py -d ./Downloaded --srt \
    --sense-voice ./sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/model.int8.onnx \
    --tokens ./sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/tokens.txt \
    --silero-vad-model ./silero_vad.onnx

  python sensevoice_transcribe.py -f video.mp4 --srt --num-threads 4 \
    --sense-voice ./model.int8.onnx --tokens ./tokens.txt --silero-vad-model ./silero_vad.onnx
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
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
        banner.append("  🎙  SenseVoice 字幕转录工具\n", style="bold bright_green")
        banner.append("  ── Video → Text/SRT via sherpa-onnx + SenseVoice ──", style="dim bright_green")
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
            detail=f"共 {total} 个文件",
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
            self._file_desc("VAD/识别"),
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


@dataclass
class Segment:
    start: float
    end: float
    text: str


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


def clean_text(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"<\|[^>]+?\|>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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


def split_segment(seg: Segment, max_chars: int) -> List[Segment]:
    chunks = split_text_for_srt(seg.text, max_chars=max_chars)
    if not chunks:
        return []
    if len(chunks) == 1:
        return [Segment(seg.start, seg.end, chunks[0])]

    total_chars = sum(max(1, len(c)) for c in chunks)
    duration = max(0.2, seg.end - seg.start)
    out: List[Segment] = []
    cur = seg.start
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            nxt = seg.end
        else:
            nxt = min(seg.end, cur + duration * (max(1, len(chunk)) / total_chars))
        if nxt <= cur:
            nxt = cur + 0.2
        out.append(Segment(cur, nxt, chunk))
        cur = nxt
    return out


def write_srt(path: Path, segments: List[Segment], converter: Any = None, max_chars: int = 24) -> None:
    lines: List[str] = []
    last_end = 0.0
    cue_index = 1
    for raw in segments:
        for seg in split_segment(raw, max_chars=max_chars):
            start = max(0.0, seg.start)
            end = max(start + 0.2, seg.end)
            if start < last_end:
                start = last_end
                end = max(end, start + 0.2)
            last_end = end
            text = converter.convert(seg.text) if converter else seg.text
            text = clean_text(text)
            if not text:
                continue
            lines.append(f"{cue_index}\n{_format_srt_time(start)} --> {_format_srt_time(end)}\n{text}\n")
            cue_index += 1
    path.write_text("\n".join(lines), encoding="utf-8")


def write_txt(path: Path, segments: List[Segment], converter: Any = None) -> None:
    text = "\n".join(clean_text(converter.convert(s.text) if converter else s.text) for s in segments if clean_text(s.text))
    path.write_text(text.strip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_output_dir(video_path: Path, output_dir: Optional[str]) -> Path:
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = None
        try:
            candidate = video_path.parent
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".sensevoice_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            out_dir = candidate
        except Exception:
            out_dir = None
        if out_dir is None:
            out_dir = Path("./transcripts")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


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


def assert_file(path: str, label: str) -> None:
    if not path:
        display.dep_fail(label, "必须提供模型路径")
        sys.exit(1)
    if not Path(path).is_file():
        display.dep_fail(label, f"文件不存在: {path}")
        sys.exit(1)


def create_recognizer(args: argparse.Namespace):
    import sherpa_onnx

    assert_file(args.sense_voice, "SenseVoice ONNX")
    assert_file(args.tokens, "tokens.txt")
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=args.sense_voice,
        tokens=args.tokens,
        num_threads=args.num_threads,
        use_itn=not args.no_itn,
        debug=args.debug,
    )


def create_vad(args: argparse.Namespace):
    import sherpa_onnx

    assert_file(args.silero_vad_model, "silero_vad.onnx")
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = args.silero_vad_model
    config.silero_vad.threshold = args.vad_threshold
    config.silero_vad.min_silence_duration = args.min_silence_duration
    config.silero_vad.min_speech_duration = args.min_speech_duration
    config.silero_vad.max_speech_duration = args.max_speech_duration
    config.sample_rate = args.sample_rate
    return sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=args.vad_buffer_seconds), config.silero_vad.window_size


def transcribe_with_sherpa(
    input_path: Path,
    recognizer: Any,
    args: argparse.Namespace,
    ffmpeg_path: str,
) -> tuple[List[Segment], float, float]:
    import sherpa_onnx

    vad, window_size = create_vad(args)

    cmd = [
        ffmpeg_path,
        "-i", str(input_path),
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", str(args.sample_rate),
        "-",
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if process.stdout is None:
        raise RuntimeError("ffmpeg stdout is empty")

    frames_per_read = int(args.sample_rate * args.read_seconds)
    buffer = np.array([], dtype=np.float32)
    segments: List[Segment] = []
    num_processed_samples = 0
    start_t = dt.datetime.now()

    while True:
        data = process.stdout.read(frames_per_read * 2)
        if not data:
            vad.flush()
            break

        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        num_processed_samples += int(samples.shape[0])
        buffer = np.concatenate([buffer, samples])

        while len(buffer) > window_size:
            vad.accept_waveform(buffer[:window_size])
            buffer = buffer[window_size:]

        while not vad.empty():
            front = vad.front
            start = float(front.start) / float(args.sample_rate)
            duration = float(len(front.samples)) / float(args.sample_rate)

            stream = recognizer.create_stream()
            stream.accept_waveform(args.sample_rate, front.samples)
            recognizer.decode_stream(stream)
            text = clean_text(stream.result.text)

            if text and text not in (".", "The."):
                segments.append(Segment(start=start, end=start + duration, text=text))
            vad.pop()

    # Process any remaining VAD chunks after flush.
    while not vad.empty():
        front = vad.front
        start = float(front.start) / float(args.sample_rate)
        duration = float(len(front.samples)) / float(args.sample_rate)
        stream = recognizer.create_stream()
        stream.accept_waveform(args.sample_rate, front.samples)
        recognizer.decode_stream(stream)
        text = clean_text(stream.result.text)
        if text and text not in (".", "The."):
            segments.append(Segment(start=start, end=start + duration, text=text))
        vad.pop()

    rc = process.wait()
    if rc not in (0, None):
        raise RuntimeError(f"ffmpeg failed, returncode={rc}")

    elapsed = (dt.datetime.now() - start_t).total_seconds()
    duration = float(num_processed_samples) / float(args.sample_rate) if num_processed_samples else 0.0
    return segments, duration, elapsed


def transcribe_file(
    video_path: Path,
    recognizer: Any,
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
    json_path = out_dir / f"{stem}.transcript.sensevoice.json"

    display.advance_file("识别中", "VAD + SenseVoice")
    segments, duration, elapsed = transcribe_with_sherpa(video_path, recognizer, args, ffmpeg_path)

    if not segments:
        display.advance_file("无内容", "未检测到语音")
        return False

    rtf = elapsed / duration if duration > 0 else 0.0
    display.advance_file("保存", f"{len(segments)}段 · RTF={rtf:.3f}")

    saved = []
    if "txt" in output_formats:
        write_txt(txt_path, segments, converter=converter)
        saved.append(txt_path.name)
    if "srt" in output_formats:
        write_srt(srt_path, segments, converter=converter, max_chars=args.max_chars)
        saved.append(srt_path.name)
    if args.json:
        payload = {
            "source": str(video_path),
            "duration": duration,
            "elapsed": elapsed,
            "rtf": rtf,
            "segments": [s.__dict__ for s in segments],
        }
        write_json(json_path, payload)
        saved.append(json_path.name)

    display.advance_file("完成", " + ".join(saved))
    return True


def main():
    parser = argparse.ArgumentParser(
        description="SenseVoiceSmall/sherpa-onnx 批量字幕转录工具 — 视频/音频 → TXT/SRT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python sensevoice_transcribe.py -d ./Downloaded --srt \\\n"
            "    --sense-voice ./model.int8.onnx --tokens ./tokens.txt --silero-vad-model ./silero_vad.onnx\n"
            "  python sensevoice_transcribe.py -f video.mp4 --srt --num-threads 4 \\\n"
            "    --sense-voice ./model.int8.onnx --tokens ./tokens.txt --silero-vad-model ./silero_vad.onnx"
        ),
    )
    parser.add_argument("-d", "--dir", default="./Downloaded", help="视频/音频目录 (默认 ./Downloaded/)")
    parser.add_argument("-f", "--file", help="单个视频/音频文件")
    parser.add_argument("-o", "--output", default=None, help="转录文件输出目录")
    parser.add_argument("--srt", action="store_true", help="同时输出 SRT 字幕")
    parser.add_argument("--json", action="store_true", help="同时保存中间 segments JSON")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已有 transcript 的视频")
    parser.add_argument("--sc", action="store_true", help="繁体转简体 (需 pip install OpenCC)")

    parser.add_argument("--sense-voice", required=True, help="SenseVoice ONNX 模型路径，建议 model.int8.onnx")
    parser.add_argument("--tokens", required=True, help="tokens.txt 路径")
    parser.add_argument("--silero-vad-model", required=True, help="silero_vad.onnx 路径")
    parser.add_argument("--num-threads", type=int, default=max(1, min(4, os.cpu_count() or 2)), help="ONNX 推理线程数")
    parser.add_argument("--sample-rate", type=int, default=16000, help="采样率，SenseVoice 通常用 16000")
    parser.add_argument("--read-seconds", type=float, default=60.0, help="每次从 ffmpeg 管道读取多少秒音频")
    parser.add_argument("--max-chars", type=int, default=24, help="SRT 单条最大字数")
    parser.add_argument("--no-itn", action="store_true", help="禁用 SenseVoice ITN/标点")
    parser.add_argument("--debug", action="store_true", help="开启 sherpa-onnx debug")

    parser.add_argument("--vad-threshold", type=float, default=0.2, help="Silero VAD threshold")
    parser.add_argument("--min-silence-duration", type=float, default=0.25, help="VAD 最短静音秒数")
    parser.add_argument("--min-speech-duration", type=float, default=0.25, help="VAD 最短语音秒数")
    parser.add_argument("--max-speech-duration", type=float, default=5.0, help="VAD 单段最长语音秒数；字幕建议 4~8")
    parser.add_argument("--vad-buffer-seconds", type=float, default=100.0, help="VAD buffer seconds")

    args = parser.parse_args()

    display.show_banner()
    console.print(f"  [{THEME['dim']}]检查依赖...[/]")

    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        display.dep_fail("ffmpeg", "conda install -c conda-forge ffmpeg 或放 ffmpeg.exe 到同目录")
        sys.exit(1)
    display.dep_ok("ffmpeg", ffmpeg_path)

    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        display.dep_fail("sherpa-onnx", "pip install -U sherpa-onnx numpy")
        sys.exit(1)
    display.dep_ok("sherpa-onnx", "已安装")

    converter = load_converter(args.sc)
    if converter:
        display.dep_ok("OpenCC", "繁体→简体")

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
    display.info(f"加载 SenseVoice ONNX: [{THEME['model']}]{Path(args.sense_voice).name}[/]")
    recognizer = create_recognizer(args)
    display.success("SenseVoice 识别器加载完成")
    console.print()

    output_formats = {"txt"}
    if args.srt:
        output_formats.add("srt")

    display.start_session(len(videos))
    try:
        for i, video in enumerate(videos, 1):
            display.start_file(i, video.name)
            try:
                ok = transcribe_file(video, recognizer, ffmpeg_path, output_formats, converter, args.output, args)
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
