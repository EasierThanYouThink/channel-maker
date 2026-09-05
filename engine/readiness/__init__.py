"""CHANNEL_READY readiness checklist: advisory evidence, re-reading already-recorded human decisions."""

from .checklist import ReadinessError, check_readiness, write_readiness_report

__all__ = ["ReadinessError", "check_readiness", "write_readiness_report"]
