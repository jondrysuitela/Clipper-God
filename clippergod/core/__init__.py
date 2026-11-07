"""Mesin inti ClipperGod (murni Python, tanpa dependensi eksternal)."""

from .boundaries import (
    BoundaryConfig,
    enforce,
    extend_for_reaction,
    find_boundaries,
    is_greeting_opening,
    score_boundary,
    snap,
)
from .captions import (
    CaptionStyle,
    build_ass,
    build_cues,
    caption_report,
    choose_placement,
    place_cues,
)
from .models import (
    Boundary,
    BoundedClip,
    CaptionCue,
    ClipCandidate,
    FaceBox,
    Segment,
    Word,
)
from .scoring import ClipSignals, VPSResult, VPSWeights, evaluate, hook_token_hits

__all__ = [
    "Boundary",
    "BoundaryConfig",
    "BoundedClip",
    "CaptionCue",
    "CaptionStyle",
    "ClipCandidate",
    "ClipSignals",
    "FaceBox",
    "Segment",
    "VPSResult",
    "VPSWeights",
    "Word",
    "build_ass",
    "build_cues",
    "caption_report",
    "choose_placement",
    "enforce",
    "evaluate",
    "extend_for_reaction",
    "find_boundaries",
    "hook_token_hits",
    "is_greeting_opening",
    "place_cues",
    "score_boundary",
    "snap",
]
