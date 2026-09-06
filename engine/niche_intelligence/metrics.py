"""Transparent, versioned Niche Intelligence measurements."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any

METRIC_VERSION = "relative_views_same_channel.v1"
MISSING_BEHAVIOR = (
    "EXCLUDE_NULL_BASELINE_VALUES; RETURN_NOT_COMPUTABLE_IF_TARGET_MISSING_OR_NO_POSITIVE_BASELINE"
)


class MetricError(ValueError):
    """A metric request is malformed or asks for an unsupported formula."""


def _rounded(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _quality(count: int) -> str:
    if count >= 5:
        return "HIGH"
    if count >= 3:
        return "MEDIUM"
    if count >= 1:
        return "LOW"
    return "INSUFFICIENT"


def relative_views_same_channel_v1(
    *,
    artifact_id: str,
    study_id: str,
    channel_id: str,
    target_video_evidence_id: str,
    target_views: int | None,
    comparison_video_evidence_ids: Sequence[str],
    baseline_views: Sequence[int | None],
    window_from: str,
    window_to: str,
    created_by: dict[str, Any],
    metric_version: str = METRIC_VERSION,
) -> dict[str, Any]:
    """Compare views with a same-channel median without implying causality.

    Null baseline values are retained in the inputs/provenance but excluded from the
    median. The percentile is the share of usable baseline observations at or below
    the target. Results are rounded to six decimal places for stable JSON output.
    """

    if metric_version != METRIC_VERSION:
        raise MetricError(f"unsupported metric version: {metric_version}")
    if len(comparison_video_evidence_ids) != len(baseline_views):
        raise MetricError("comparison IDs and baseline views must have equal length")
    if len(set(comparison_video_evidence_ids)) != len(comparison_video_evidence_ids):
        raise MetricError("comparison video IDs must be unique")
    if target_views is not None and target_views < 0:
        raise MetricError("target views must be null or non-negative")
    if any(value is not None and value < 0 for value in baseline_views):
        raise MetricError("baseline views must be null or non-negative")

    usable = [value for value in baseline_views if value is not None]
    baseline_quality = _quality(len(usable))
    status = "COMPUTED"
    reason = None
    baseline_median: float | None = None
    ratio: float | None = None
    percentile: float | None = None
    breakout: float | None = None
    if target_views is None:
        status = "NOT_COMPUTABLE"
        reason = "target views are unknown"
    elif not usable:
        status = "NOT_COMPUTABLE"
        reason = "no usable baseline views"
    else:
        median_value = Decimal(str(median(usable)))
        baseline_median = _rounded(median_value)
        if median_value <= 0:
            status = "NOT_COMPUTABLE"
            reason = "baseline median must be positive"
        else:
            ratio_decimal = Decimal(target_views) / median_value
            ratio = _rounded(ratio_decimal)
            breakout = _rounded(ratio_decimal - Decimal(1))
            at_or_below = sum(value <= target_views for value in usable)
            percentile = _rounded(Decimal(at_or_below) / Decimal(len(usable)))

    return {
        "schema_version": "1.0.0",
        "artifact_type": "relative_performance",
        "artifact_id": artifact_id,
        "study_id": study_id,
        "channel_id": channel_id,
        "authority": "DERIVED_MEASUREMENT",
        "metric_version": METRIC_VERSION,
        "target_video_evidence_id": target_video_evidence_id,
        "inputs": {"target_views": target_views, "baseline_views": list(baseline_views)},
        "comparison": {
            "population_video_evidence_ids": list(comparison_video_evidence_ids),
            "window": {"from": window_from, "to": window_to},
            "baseline_statistic": "MEDIAN",
            "baseline_quality": baseline_quality,
        },
        "missing_data_behavior": MISSING_BEHAVIOR,
        "status": status,
        "result": {
            "baseline_median_views": baseline_median,
            "relative_views_ratio": ratio,
            "percentile_within_comparison": percentile,
            "breakout_magnitude": breakout,
            "reason": reason,
        },
        "created_by": created_by,
    }
