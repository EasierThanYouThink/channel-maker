"""Canonical V1 channel-creation workflow vocabulary and transition rules."""

from __future__ import annotations

import hashlib
import json
from typing import Any


WORKFLOW_STATES = (
    "CHANNEL_INIT",
    "NICHE_INTELLIGENCE",
    "OPPORTUNITY_MAP",
    "STRATEGY_SELECTION",
    "CHANNEL_FOUNDATION",
    "SCRIPT_DNA_DISCOVERY",
    "VISUAL_DNA_DISCOVERY",
    "MOTION_DNA_DISCOVERY",
    "CHANNEL_IDENTITY",
    "STARTER_VISUAL_LIBRARY",
    "PILOT_PLAN",
    "PILOT_PRODUCTION",
    "PILOT_REVIEW",
    "CHANNEL_FREEZE",
    "CHANNEL_READY",
)

FORWARD_TRANSITIONS = dict(zip(WORKFLOW_STATES, WORKFLOW_STATES[1:]))

HUMAN_GATE_TRANSITIONS = {
    ("OPPORTUNITY_MAP", "STRATEGY_SELECTION"),
    ("PILOT_REVIEW", "CHANNEL_FREEZE"),
}

REVISION_TARGETS = frozenset({
    "STRATEGY_SELECTION",
    "CHANNEL_FOUNDATION",
    "SCRIPT_DNA_DISCOVERY",
    "VISUAL_DNA_DISCOVERY",
    "MOTION_DNA_DISCOVERY",
    "CHANNEL_IDENTITY",
    "STARTER_VISUAL_LIBRARY",
    "PILOT_PLAN",
    "PILOT_PRODUCTION",
})

# Artifact families a revision puts back under review. Frozen artifacts are
# not auto-unfrozen — only the state pointer moves — but the families name
# what must be re-approved on the way forward. Ordered outer to inner.
REVISION_INVALIDATIONS = {
    "STRATEGY_SELECTION": ("strategy", "foundation", "script-dna", "design-dna", "identity", "library", "pilot"),
    "CHANNEL_FOUNDATION": ("foundation", "script-dna", "design-dna", "identity", "library", "pilot"),
    "SCRIPT_DNA_DISCOVERY": ("script-dna", "pilot",),
    "VISUAL_DNA_DISCOVERY": ("visual-dna", "identity", "library", "pilot"),
    "MOTION_DNA_DISCOVERY": ("motion-dna", "pilot"),
    "CHANNEL_IDENTITY": ("identity", "library", "pilot"),
    "STARTER_VISUAL_LIBRARY": ("library", "pilot"),
    "PILOT_PLAN": ("pilot-plan", "pilot"),
    "PILOT_PRODUCTION": ("pilot",),
}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def event_id_for(event_without_id: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(event_without_id)).hexdigest()
    return f"channel-event-{digest[:16]}"


def completed_prefix_for(state: str) -> list[str]:
    return list(WORKFLOW_STATES[: WORKFLOW_STATES.index(state)])
