from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from server.subtitle_jobs import SubtitleJob, SubtitleJobManager
from subtitle.ass_converter import convert_srt_to_ass
from subtitle.burner import burn_ass
from subtitle.mask import build_masked_subtitle_filter
from subtitle.models import MaskRect
from subtitle.pipeline import SubtitlePipeline
from subtitle.srt_parser import parse_srt, validate_same_timing, write_srt
from subtitle.style import AssStyle
from subtitle.translator import create_translator, translate_cues


class SubtitleJobResponse(BaseModel):
    job_id: str
    status: str
    type: str


class TranslateSubtitleRequest(BaseModel):
    input_srt_path: str
    output_srt_path: str
    source_lang: str = "zh"
    target_lang: str = "vi"
    translator: str = "noop"
    batch_size: int = 20


class ConvertAssRequest(BaseModel):
    input_srt_path: str
    output_ass_path: str
    style_preset: str = "douyin_vi"
    style: Dict[str, Any] = {}


class MaskRequest(BaseModel):
    mode: str = "none"
    rect: Optional[Dict[str, int]] = None
    blur_strength: int = 12
    box_color: str = "black@0.85"


class BurnSubtitleRequest(BaseModel):
    video_path: str
    ass_path: str
    output_video_path: str
    ffmpeg_path: str = ""
    fonts_dir: str = ""
    mask: MaskRequest = Field(default_factory=MaskRequest)


class PipelineSubtitleRequest(BaseModel):
    video_path: str
    input_srt_path: str
    output_video_path: str = ""
    output_dir: str = ""
    source_lang: str = "zh"
    target_lang: str = "vi"
    translator: str = "noop"
    batch_size: int = 20
    style_preset: str = "douyin_vi"
    ffmpeg_path: str = ""
    fonts_dir: str = ""
    burn: bool = True
    mask: MaskRequest = Field(default_factory=MaskRequest)


def register_subtitle_routes(app: FastAPI, config: Any) -> SubtitleJobManager:
    async def executor(job: SubtitleJob) -> Dict[str, Any]:
        payload = job.payload
        if job.type == "subtitle_translate":
            return _execute_translate(payload, job)
        if job.type == "subtitle_convert_ass":
            return _execute_convert_ass(payload, config, job)
        if job.type == "subtitle_burn":
            return _execute_burn(payload, job)
        if job.type == "subtitle_pipeline":
            return _execute_pipeline(payload, config, job)
        raise RuntimeError(f"unsupported subtitle job type: {job.type}")

    server_cfg = config.get("server") or {}
    manager = SubtitleJobManager(
        executor=executor,
        max_concurrency=int(config.get("thread", 2) or 2),
        max_jobs=int(server_cfg.get("max_jobs") or SubtitleJobManager.DEFAULT_MAX_JOBS),
        job_ttl_seconds=float(
            server_cfg.get("job_ttl_seconds")
            or SubtitleJobManager.DEFAULT_JOB_TTL_SECONDS
        ),
    )
    app.state.subtitle_job_manager = manager

    @app.post("/api/v1/subtitles/translate", response_model=SubtitleJobResponse)
    async def translate(req: TranslateSubtitleRequest) -> SubtitleJobResponse:
        job = await manager.submit("subtitle_translate", req.model_dump())
        return SubtitleJobResponse(job_id=job.job_id, status=job.status, type=job.type)

    @app.post("/api/v1/subtitles/convert-ass", response_model=SubtitleJobResponse)
    async def convert_ass(req: ConvertAssRequest) -> SubtitleJobResponse:
        job = await manager.submit("subtitle_convert_ass", req.model_dump())
        return SubtitleJobResponse(job_id=job.job_id, status=job.status, type=job.type)

    @app.post("/api/v1/subtitles/burn", response_model=SubtitleJobResponse)
    async def burn(req: BurnSubtitleRequest) -> SubtitleJobResponse:
        job = await manager.submit("subtitle_burn", req.model_dump())
        return SubtitleJobResponse(job_id=job.job_id, status=job.status, type=job.type)

    @app.post("/api/v1/subtitles/pipeline", response_model=SubtitleJobResponse)
    async def pipeline(req: PipelineSubtitleRequest) -> SubtitleJobResponse:
        job = await manager.submit("subtitle_pipeline", req.model_dump())
        return SubtitleJobResponse(job_id=job.job_id, status=job.status, type=job.type)

    return manager


async def get_subtitle_job_or_404(app: FastAPI, job_id: str) -> Optional[Dict[str, Any]]:
    manager = getattr(app.state, "subtitle_job_manager", None)
    if manager is None:
        return None
    job = await manager.get(job_id)
    if job is None:
        return None
    return job.to_dict()


async def shutdown_subtitle_jobs(app: FastAPI) -> None:
    manager = getattr(app.state, "subtitle_job_manager", None)
    if manager is not None:
        await manager.shutdown()


def _execute_translate(payload: Dict[str, Any], job: SubtitleJob) -> Dict[str, Any]:
    job.set_progress("parse", 1, 3, "Parsing SRT")
    cues = parse_srt(Path(payload["input_srt_path"]))
    job.set_progress("translate", 2, 3, "Translating")
    translated = translate_cues(
        cues,
        create_translator(payload.get("translator", "noop")),
        source_lang=payload.get("source_lang", "zh"),
        target_lang=payload.get("target_lang", "vi"),
        batch_size=int(payload.get("batch_size") or 20),
    )
    validate_same_timing(cues, translated)
    output = Path(payload["output_srt_path"])
    write_srt(output, translated)
    job.set_progress("done", 3, 3, "Done")
    return {"status": "success", "stage": "done", "outputs": {"translated_srt": str(output)}}


def _execute_convert_ass(payload: Dict[str, Any], config: Any, job: SubtitleJob) -> Dict[str, Any]:
    job.set_progress("convert_ass", 1, 1, "Converting SRT to ASS")
    style = AssStyle.from_config(
        config.get("subtitle", {}) if hasattr(config, "get") else {},
        preset_name=payload.get("style_preset", "douyin_vi"),
        overrides=payload.get("style") or {},
    )
    output = Path(payload["output_ass_path"])
    convert_srt_to_ass(Path(payload["input_srt_path"]), output, style)
    return {"status": "success", "stage": "done", "outputs": {"ass": str(output)}}


def _execute_burn(payload: Dict[str, Any], job: SubtitleJob) -> Dict[str, Any]:
    job.set_progress("burn", 1, 1, "Burning ASS")
    mask = payload.get("mask") or {}
    rect = _rect_from_payload(mask.get("rect"))
    video_filter = build_masked_subtitle_filter(
        ass_path=Path(payload["ass_path"]),
        fonts_dir=payload.get("fonts_dir", ""),
        mode=mask.get("mode", "none"),
        rect=rect,
        box_color=mask.get("box_color", "black@0.85"),
        blur_strength=int(mask.get("blur_strength") or 12),
    )
    output = Path(payload["output_video_path"])
    burn_ass(
        video_path=Path(payload["video_path"]),
        ass_path=Path(payload["ass_path"]),
        output_path=output,
        ffmpeg_path=payload.get("ffmpeg_path", ""),
        fonts_dir=payload.get("fonts_dir", ""),
        video_filter=video_filter,
    )
    return {"status": "success", "stage": "done", "outputs": {"video": str(output)}}


def _execute_pipeline(payload: Dict[str, Any], config: Any, job: SubtitleJob) -> Dict[str, Any]:
    mask = payload.get("mask") or {}
    result = SubtitlePipeline(progress_callback=job.set_progress).run(
        video_path=Path(payload["video_path"]),
        input_srt_path=Path(payload["input_srt_path"]),
        output_video_path=Path(payload["output_video_path"]) if payload.get("output_video_path") else None,
        output_dir=Path(payload.get("output_dir") or Path(payload["input_srt_path"]).parent),
        source_lang=payload.get("source_lang", "zh"),
        target_lang=payload.get("target_lang", "vi"),
        translator_name=payload.get("translator", "noop"),
        batch_size=int(payload.get("batch_size") or 20),
        style_preset=payload.get("style_preset", "douyin_vi"),
        subtitle_config=config.get("subtitle", {}) if hasattr(config, "get") else {},
        mask_mode=mask.get("mode", "none"),
        mask_rect=_rect_from_payload(mask.get("rect")),
        ffmpeg_path=payload.get("ffmpeg_path", ""),
        fonts_dir=payload.get("fonts_dir", ""),
        burn=bool(payload.get("burn", True)),
    )
    return result.to_dict()


def _rect_from_payload(raw: Optional[Dict[str, int]]) -> Optional[MaskRect]:
    if raw is None:
        return None
    try:
        return MaskRect(
            x=int(raw["x"]),
            y=int(raw["y"]),
            w=int(raw["w"]),
            h=int(raw["h"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing mask rect field: {exc}")
