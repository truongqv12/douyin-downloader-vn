from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AssStyle:
    name: str = "Default"
    font: str = "Noto Sans"
    font_size: int = 42
    primary_color: str = "&H00FFFFFF"
    secondary_color: str = "&H000000FF"
    outline_color: str = "&H00000000"
    back_color: str = "&H99000000"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikeout: bool = False
    scale_x: int = 100
    scale_y: int = 100
    spacing: int = 0
    angle: int = 0
    border_style: int = 1
    outline: int = 2
    shadow: int = 1
    alignment: int = 2
    margin_l: int = 40
    margin_r: int = 40
    margin_v: int = 70
    encoding: int = 1
    wrap_style: int = 0

    @classmethod
    def from_config(
        cls,
        config: Optional[Dict[str, Any]],
        *,
        preset_name: str = "douyin_vi",
        overrides: Optional[Dict[str, Any]] = None,
    ) -> "AssStyle":
        data: Dict[str, Any] = {}
        if isinstance(config, dict):
            style_cfg = config.get("style") or {}
            presets = style_cfg.get("presets") or {}
            if isinstance(presets, dict):
                data.update(presets.get(preset_name) or {})
            direct = {k: v for k, v in style_cfg.items() if k != "presets"}
            data.update(direct)
        if overrides:
            data.update({k: v for k, v in overrides.items() if v is not None})
        if "preset" in data:
            data.pop("preset")
        return cls(
            name=str(_get_value(data, "name", "Default")),
            font=str(_get_value(data, "font", "Noto Sans")),
            font_size=_get_int_any(data, ("font_size", "font-size"), 42),
            primary_color=str(_get_value(data, "primary_color", "&H00FFFFFF")),
            secondary_color=str(_get_value(data, "secondary_color", "&H000000FF")),
            outline_color=str(_get_value(data, "outline_color", "&H00000000")),
            back_color=str(_get_value(data, "back_color", "&H99000000")),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            underline=bool(data.get("underline", False)),
            strikeout=bool(data.get("strikeout", False)),
            scale_x=_get_int(data, "scale_x", 100),
            scale_y=_get_int(data, "scale_y", 100),
            spacing=_get_int(data, "spacing", 0),
            angle=_get_int(data, "angle", 0),
            border_style=_get_int(data, "border_style", 1),
            outline=_get_int(data, "outline", 2),
            shadow=_get_int(data, "shadow", 1),
            alignment=_get_int(data, "alignment", 2),
            margin_l=_get_int(data, "margin_l", 40),
            margin_r=_get_int(data, "margin_r", 40),
            margin_v=_get_int(data, "margin_v", 70),
            encoding=_get_int(data, "encoding", 1),
            wrap_style=_get_int(data, "wrap_style", 0),
        )

    def to_ass_style_line(self) -> str:
        return ",".join(
            [
                self.name,
                self.font,
                str(self.font_size),
                self.primary_color,
                self.secondary_color,
                self.outline_color,
                self.back_color,
                _ass_bool(self.bold),
                _ass_bool(self.italic),
                _ass_bool(self.underline),
                _ass_bool(self.strikeout),
                str(self.scale_x),
                str(self.scale_y),
                str(self.spacing),
                str(self.angle),
                str(self.border_style),
                str(self.outline),
                str(self.shadow),
                str(self.alignment),
                str(self.margin_l),
                str(self.margin_r),
                str(self.margin_v),
                str(self.encoding),
            ]
        )


def _ass_bool(value: bool) -> str:
    return "-1" if value else "0"


def _get_value(data: Dict[str, Any], key: str, default: Any) -> Any:
    return data[key] if key in data and data[key] is not None else default


def _get_int(data: Dict[str, Any], key: str, default: int) -> int:
    return int(_get_value(data, key, default))


def _get_int_any(data: Dict[str, Any], keys: tuple[str, ...], default: int) -> int:
    for key in keys:
        if key in data and data[key] is not None:
            return int(data[key])
    return default
