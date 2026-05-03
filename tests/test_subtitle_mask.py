import pytest

from subtitle.errors import SubtitleParseError
from subtitle.mask import (
    build_blur_filter,
    build_box_filter,
    build_crop_filter,
    build_masked_subtitle_filter,
    scale_rect_from_display,
)
from subtitle.models import MaskRect


def test_mask_rect_parse_and_bounds():
    rect = MaskRect.parse("0,880,1080,180")
    rect.validate_bounds(1080, 1920)

    with pytest.raises(SubtitleParseError):
        rect.validate_bounds(1000, 1000)


def test_box_crop_blur_filter_strings():
    rect = MaskRect(0, 880, 1080, 180)

    assert build_box_filter(rect) == (
        "drawbox=x=0:y=880:w=1080:h=180:color=black@0.85:t=fill"
    )
    assert build_crop_filter(rect) == "crop=iw:880:0:0"
    assert build_blur_filter(rect) == (
        "split[base][crop];"
        "[crop]crop=1080:180:0:880,boxblur=12:1[blur];"
        "[base][blur]overlay=0:880"
    )


def test_crop_filter_requires_subtitle_top_below_first_row():
    with pytest.raises(SubtitleParseError):
        build_crop_filter(MaskRect(0, 0, 1080, 180))


def test_masked_subtitle_filter_requires_rect():
    with pytest.raises(SubtitleParseError):
        build_masked_subtitle_filter(ass_path="sub.ass", mode="box")


def test_scale_rect_from_display_maps_to_video_coordinates():
    rect = scale_rect_from_display(
        MaskRect(0, 440, 540, 90),
        display_width=540,
        display_height=960,
        video_width=1080,
        video_height=1920,
    )

    assert rect == MaskRect(0, 880, 1080, 180)
