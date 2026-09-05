"""Assemble one provider-neutral request describing what Hermes Agent should collect."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _core import TOOL_VERSION, ChannelMakerError, content_hash, write_json_atomic


CHANNEL_PUBLIC_FIELDS = ["subscriber_count", "public_video_count", "created_at", "observed_uploads_per_30d", "shorts_fraction"]
VIDEO_PUBLIC_FIELDS = ["published_at", "duration_seconds", "views", "likes", "comment_count", "description", "age_at_observation_days"]
BOUNDARY_INSTRUCTIONS = [
    "Collect PUBLIC facts only: never record CTR, retention curve, swipe-away rate, average percentage "
    "viewed, traffic sources, or subscriber conversion — those are private analytics and must never appear here.",
    "Leave a field null and note it as unknown rather than guessing or estimating a value.",
    "Every source URL must be public and start with https://.",
    "Assign a sample role and a one-sentence rationale for every channel/video you collect.",
    "Do not copy scripts, thumbnails, or other protected expression — only structured public metadata/statistics.",
    "reference_channels (max 3) are studied for calibration only — what formats, pacing, and topics are "
    "working. Record their public metadata like any other evidence; never reproduce their expression.",
]

MAX_REFERENCE_CHANNELS = 3


def _check_reference_channel(value: str) -> str:
    text = value.strip()
    if not text:
        raise ChannelMakerError("reference channel must not be empty")
    if not (text.startswith("https://") or text.startswith("@")):
        raise ChannelMakerError(
            f"reference channel must be a public https:// URL or an @handle: {value!r}"
        )
    return text


def build_request(
    *,
    channel_id: str,
    study_id: str,
    target: str,
    sample_size_hint: int,
    allowed_channel_roles: list[str],
    allowed_video_roles: list[str],
    output: Path,
    reference_channels: list[str] | None = None,
) -> Path:
    # v1 is CREATE-only (niche keywords). CLONE (single target channel) returns in v2.
    mode = "CREATE"
    references = [_check_reference_channel(item) for item in (reference_channels or [])]
    if len(references) > MAX_REFERENCE_CHANNELS:
        raise ChannelMakerError(
            f"at most {MAX_REFERENCE_CHANNELS} reference channels per request, got {len(references)}"
        )
    request_core = {
        "mode": mode, "channel_id": channel_id, "study_id": study_id, "target": target,
        "sample_size_hint": sample_size_hint, "reference_channels": references,
    }
    digest = content_hash(request_core)
    request: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": "hermes_collection_request",
        "artifact_id": f"hermes-request:{channel_id}:{study_id}:{digest[:12]}",
        **request_core,
        "requested_channel_fields": CHANNEL_PUBLIC_FIELDS,
        "requested_video_fields": VIDEO_PUBLIC_FIELDS,
        "allowed_channel_roles": allowed_channel_roles,
        "allowed_video_roles": allowed_video_roles,
        "instructions": BOUNDARY_INSTRUCTIONS,
        "created_by": {"tool": "radicat.build_niche_collection_request", "version": TOOL_VERSION},
    }
    write_json_atomic(output, request)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--study-id", required=True)
    parser.add_argument("--target", required=True, help="Niche keywords describing what Hermes should collect (v1 CREATE-only)")
    parser.add_argument(
        "--reference-channel", action="append", default=[], dest="reference_channels",
        help="Competitor channel to study for calibration (public https:// URL or @handle). "
             f"Repeatable, max {MAX_REFERENCE_CHANNELS}. Study what's working; never copy expression.",
    )
    parser.add_argument("--sample-size-hint", type=int, default=10)
    parser.add_argument(
        "--allowed-channel-role", action="append", required=True, dest="allowed_channel_roles",
        choices=["ESTABLISHED_LEADER", "GROWTH_CANDIDATE", "SMALL_BREAKOUT", "BASELINE_COMPARATOR", "OTHER", "UNKNOWN"],
    )
    parser.add_argument(
        "--allowed-video-role", action="append", required=True, dest="allowed_video_roles",
        choices=["BREAKOUT", "CHANNEL_BASELINE", "RECENT_NORMAL", "UNDERPERFORMER", "OUTLIER", "OTHER", "UNKNOWN"],
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = build_request(
            channel_id=args.channel_id, study_id=args.study_id, target=args.target,
            sample_size_hint=args.sample_size_hint, allowed_channel_roles=args.allowed_channel_roles,
            allowed_video_roles=args.allowed_video_roles, output=args.output,
            reference_channels=args.reference_channels,
        )
    except ChannelMakerError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
