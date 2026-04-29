import time

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from config import ConfigLoader
from server.app import build_app


def test_subtitle_translate_endpoint_creates_job_and_reports_outputs(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)

    input_srt = tmp_path / "input.srt"
    output_srt = tmp_path / "input.vi.srt"
    input_srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/subtitles/translate",
            json={
                "input_srt_path": str(input_srt),
                "output_srt_path": str(output_srt),
                "translator": "noop",
            },
        )
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        _wait_for_subtitle_job(client, job_id)

        detail = client.get(f"/api/v1/jobs/{job_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "success"
        assert payload["outputs"]["translated_srt"] == str(output_srt)


def test_subtitle_pipeline_endpoint_no_burn(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)

    input_srt = tmp_path / "input.srt"
    video = tmp_path / "input.mp4"
    input_srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n你好\n", encoding="utf-8")
    video.write_bytes(b"not-a-real-video")

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/subtitles/pipeline",
            json={
                "video_path": str(video),
                "input_srt_path": str(input_srt),
                "output_dir": str(tmp_path / "out"),
                "translator": "noop",
                "burn": False,
            },
        )
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        _wait_for_subtitle_job(client, job_id)

        detail = client.get(f"/api/v1/jobs/{job_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "success"
        assert "ass" in payload["outputs"]


def _wait_for_subtitle_job(client: TestClient, job_id: str):
    deadline = time.time() + 2.0
    while time.time() < deadline:
        payload = client.get(f"/api/v1/jobs/{job_id}").json()
        if payload["status"] in {"success", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"subtitle job did not finish: {job_id}")
