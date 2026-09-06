"""Canonical V1 channel-creation workflow vocabulary and transition rules."""

from __future__ import annotations

import hashlib
import json
from itertools import pairwise
from typing import Any

# V2 vocabulary (10 states): OPPORTUNITY_MAP folded into the
# NICHE_INTELLIGENCE -> STRATEGY_SELECTION gated edge, VISUAL + MOTION DNA
# merged into DESIGN_DNA_DISCOVERY (per-domain freeze mechanics unchanged),
# STARTER_VISUAL_LIBRARY + PILOT_PLAN folded into the CHANNEL_IDENTITY ->
# PILOT_PRODUCTION advance (component approval and pilot plan arrive as
# prerequisite refs), CHANNEL_FREEZE folded into CHANNEL_READY (freeze
# actions happen in PILOT_REVIEW post-GO; the gate moves to the READY edge).
# Both human gates survive with identical semantics, only shifted edges.
WORKFLOW_STATES = (
    "CHANNEL_INIT",
    "NICHE_INTELLIGENCE",
    "STRATEGY_SELECTION",
    "CHANNEL_FOUNDATION",
    "SCRIPT_DNA_DISCOVERY",
    "DESIGN_DNA_DISCOVERY",
    "CHANNEL_IDENTITY",
    "PILOT_PRODUCTION",
    "PILOT_REVIEW",
    "CHANNEL_READY",
)

FORWARD_TRANSITIONS = dict(pairwise(WORKFLOW_STATES))

HUMAN_GATE_TRANSITIONS = {
    ("NICHE_INTELLIGENCE", "STRATEGY_SELECTION"),
    ("PILOT_REVIEW", "CHANNEL_READY"),
}

REVISION_TARGETS = frozenset({
    "STRATEGY_SELECTION",
    "CHANNEL_FOUNDATION",
    "SCRIPT_DNA_DISCOVERY",
    "DESIGN_DNA_DISCOVERY",
    "CHANNEL_IDENTITY",
    "PILOT_PRODUCTION",
})

# Artifact families a revision puts back under review. Frozen artifacts are
# not auto-unfrozen — only the state pointer moves — but the families name
# what must be re-approved on the way forward. Ordered outer to inner.
REVISION_INVALIDATIONS = {
    "STRATEGY_SELECTION": ("strategy", "foundation", "script-dna", "design-dna", "identity", "library", "pilot"),
    "CHANNEL_FOUNDATION": ("foundation", "script-dna", "design-dna", "identity", "library", "pilot"),
    "SCRIPT_DNA_DISCOVERY": ("script-dna", "pilot",),
    "DESIGN_DNA_DISCOVERY": ("visual-dna", "motion-dna", "identity", "library", "pilot"),
    "CHANNEL_IDENTITY": ("identity", "library", "pilot"),
    "PILOT_PRODUCTION": ("pilot-plan", "pilot"),
}

# V1 (0.2.0) states dropped in the 10-state vocabulary, mapped to the
# surviving state that re-holds their evidence. Positions marked ambiguous
# need a deliberate human re-walk (mapped with legacy_mapping set, which
# blocks forward advance until migrated).
DROPPED_STATE_MAP = {
    "OPPORTUNITY_MAP": "NICHE_INTELLIGENCE",
    "VISUAL_DNA_DISCOVERY": "DESIGN_DNA_DISCOVERY",
    "MOTION_DNA_DISCOVERY": "DESIGN_DNA_DISCOVERY",
    "STARTER_VISUAL_LIBRARY": "CHANNEL_IDENTITY",
    "PILOT_PLAN": "CHANNEL_IDENTITY",
    "CHANNEL_FREEZE": "PILOT_REVIEW",
}

AMBIGUOUS_DROPPED_STATES = frozenset({
    "OPPORTUNITY_MAP",
    "PILOT_PLAN",
    "CHANNEL_FREEZE",
})


def migrate_020_to_030(state: dict[str, Any]) -> dict[str, Any]:
    """Migrate a 0.2.0 channel state document to the 10-state vocabulary.

    Pure function (no I/O): remaps dropped states in state + completed,
    rewrites event endpoints through the same map, folds ADVANCE self-loops
    produced by the merge into the following event (union of refs — the two
    advances represented one logical step under the merged vocabulary),
    then resequences, relinks, and recomputes the event chain.
    """
    import copy

    value = copy.deepcopy(state)
    old_state = value["state"]
    new_state = DROPPED_STATE_MAP.get(old_state, old_state)
    value["state"] = new_state
    value["schema_version"] = "0.3.0"
    if old_state in AMBIGUOUS_DROPPED_STATES:
        value["legacy_mapping"] = True
    if old_state == "CHANNEL_FREEZE" and value.get("status") == "ACTIVE":
        value["status"] = "REVISING"

    def remap(name: str) -> str:
        return DROPPED_STATE_MAP.get(name, name)

    # Fold merged ADVANCE self-loops forward into the next event (union of
    # refs — the two advances represented one logical step under the merged
    # vocabulary). BLOCK/RESUME/REVISE/ABANDON are same-state by design and
    # pass through untouched. A trailing self-loop carries nowhere and is
    # dropped (its refs already persist in source_refs).
    remapped = []
    for event in value.get("events", []):
        event = dict(event)
        event["from_state"] = remap(event["from_state"])
        event["to_state"] = remap(event["to_state"])
        remapped.append(event)
    kept: list[dict[str, Any]] = []
    carry: dict[str, Any] | None = None
    for event in remapped:
        if event["operation"] == "ADVANCE" and event["from_state"] == event["to_state"]:
            carry = event if carry is None else {
                **event,
                "prerequisite_refs": sorted(set(carry.get("prerequisite_refs", [])) | set(event.get("prerequisite_refs", []))),
                "human_decision_ref": carry.get("human_decision_ref") or event.get("human_decision_ref"),
            }
            continue
        if carry is not None:
            event = dict(event)
            event["prerequisite_refs"] = sorted(set(event.get("prerequisite_refs", [])) | set(carry.get("prerequisite_refs", [])))
            if not event.get("human_decision_ref") and carry.get("human_decision_ref"):
                event["human_decision_ref"] = carry["human_decision_ref"]
            carry = None
        kept.append(event)
    # A trailing self-loop carries nowhere; its refs persist in source_refs.
    events = []
    previous_id = None
    for index, event in enumerate(kept, start=1):
        event = dict(event)
        event["sequence"] = index
        event["previous_event_id"] = previous_id
        event["state_revision"] = index
        seed = {key: val for key, val in event.items() if key != "event_id"}
        event["event_id"] = event_id_for(seed)
        previous_id = event["event_id"]
        events.append(event)
    value["events"] = events
    value["revision"] = len(events)
    value["completed"] = completed_prefix_for(new_state)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def event_id_for(event_without_id: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(event_without_id)).hexdigest()
    return f"channel-event-{digest[:16]}"


def completed_prefix_for(state: str) -> list[str]:
    return list(WORKFLOW_STATES[: WORKFLOW_STATES.index(state)])
