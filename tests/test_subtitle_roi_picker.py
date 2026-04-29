import json

from subtitle.models import MaskRect
from subtitle.roi_picker import write_rect_json


def test_write_rect_json_outputs_cli_args(tmp_path):
    output = tmp_path / "mask_rect.json"

    write_rect_json(
        output,
        video_path=tmp_path / "input.mp4",
        timestamp="00:00:03",
        rect=MaskRect(0, 880, 1080, 180),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["rect"] == {"x": 0, "y": 880, "w": 1080, "h": 180}
    assert payload["cli_args"] == "--mask-mode blur --mask-rect 0,880,1080,180"
