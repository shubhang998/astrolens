"""Visual field-of-view presets for live evidence requests."""

from __future__ import annotations

from dataclasses import dataclass

from astrolens.core.enums import VisualMode


@dataclass(frozen=True)
class VisualModePreset:
    """Resolved live-retrieval knobs for a visual mode."""

    mode: VisualMode
    mast_radius_deg: float
    skyview_radius_deg: float
    pixels: int
    description: str


VISUAL_MODE_PRESETS: dict[VisualMode, VisualModePreset] = {
    VisualMode.DETAIL: VisualModePreset(
        mode=VisualMode.DETAIL,
        mast_radius_deg=0.01,
        skyview_radius_deg=0.03,
        pixels=1024,
        description="Narrow field for object detail and compact sources.",
    ),
    VisualMode.CONTEXT: VisualModePreset(
        mode=VisualMode.CONTEXT,
        mast_radius_deg=0.03,
        skyview_radius_deg=0.08,
        pixels=1024,
        description="Balanced field that preserves the previous live SkyView default.",
    ),
    VisualMode.WIDE: VisualModePreset(
        mode=VisualMode.WIDE,
        mast_radius_deg=0.08,
        skyview_radius_deg=0.20,
        pixels=1536,
        description="Wider field for extended objects and surrounding sky context.",
    ),
}


def coerce_visual_mode(value: VisualMode | str | None) -> VisualMode:
    """Normalize public visual mode input."""

    if value is None:
        return VisualMode.CONTEXT
    if isinstance(value, VisualMode):
        return value
    return VisualMode(value.strip().lower())


def visual_mode_preset(value: VisualMode | str | None) -> VisualModePreset:
    """Return the preset for a visual mode, defaulting to context."""

    return VISUAL_MODE_PRESETS[coerce_visual_mode(value)]
