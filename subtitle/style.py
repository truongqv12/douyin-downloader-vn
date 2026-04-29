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
            name=str(data.get("name") or "Default"),
            font=str(data.get("font") or "Noto Sans"),
            font_size=int(data.get("font_size") or data.get("font-size") or 42),
            primary_color=str(data.get("primary_color") or "&H00FFFFFF"),
            secondary_color=str(data.get("secondary_color") or "&H000000FF"),
            outline_color=str(data.get("outline_color") or "&H00000000"),
            back_color=str(data.get("back_color") or "&H99000000"),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            underline=bool(data.get("underline", False)),
            strikeout=bool(data.get("strikeout", False)),
            scale_x=int(data.get("scale_x") or 100),
            scale_y=int(data.get("scale_y") or 100),
            spacing=int(data.get("spacing") or 0),
            angle=int(data.get("angle") or 0),
            border_style=int(data.get("border_style") or 1),
            outline=int(data.get("outline") or 2),
            shadow=int(data.get("shadow") or 1),
            alignment=int(data.get("alignment") or 2),
            margin_l=int(data.get("margin_l") or 40),
            margin_r=int(data.get("margin_r") or 40),
            margin_v=int(data.get("margin_v") or 70),
            encoding=int(data.get("encoding") or 1),
            wrap_style=int(data.get("wrap_style") or 0),
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
