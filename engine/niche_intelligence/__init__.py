"""Offline, evidence-first Niche Intelligence contracts and APIs."""

from .acquisition import (
    add_content_annotation,
    add_hypothesis,
    add_observation,
    add_opportunity,
    add_script_annotation,
    add_visual_market_annotation,
    import_evidence,
    init_study,
)
from .metrics import MetricError, relative_views_same_channel_v1
from .repository import NicheIntelligenceRepository
from .validation import (
    COMPARATOR_VIDEO_ROLES,
    NicheValidationError,
    ValidatedStudy,
    study_coverage,
    validate_contracts,
    validate_study,
)

__all__ = [
    "COMPARATOR_VIDEO_ROLES",
    "MetricError",
    "NicheIntelligenceRepository",
    "NicheValidationError",
    "ValidatedStudy",
    "add_content_annotation",
    "add_hypothesis",
    "add_observation",
    "add_opportunity",
    "add_script_annotation",
    "add_visual_market_annotation",
    "import_evidence",
    "init_study",
    "relative_views_same_channel_v1",
    "study_coverage",
    "validate_contracts",
    "validate_study",
]
