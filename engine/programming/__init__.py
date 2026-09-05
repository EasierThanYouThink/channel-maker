"""Experimental programming desk: editorial bets tracked against outcomes.

Opportunity proposals become hypotheses with episode assignments; production
costs, publication receipts, and later outcome snapshots join them. Missing
analytics stay unknown; measurements require provenance and comparable
windows. Correlation is labeled correlation — the human approves strategic
changes and each bounded slate.
"""

from .store import (
    ProgrammingError,
    approve_slate,
    assign_episode,
    desk_root,
    list_hypotheses,
    list_slates,
    propose_hypothesis,
    propose_slate,
    record_cost,
    record_outcome,
    record_publication,
)

__all__ = [
    "ProgrammingError",
    "approve_slate",
    "assign_episode",
    "desk_root",
    "list_hypotheses",
    "list_slates",
    "propose_hypothesis",
    "propose_slate",
    "record_cost",
    "record_outcome",
    "record_publication",
]
