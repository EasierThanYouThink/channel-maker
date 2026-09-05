"""Taste compiler: conditional preferences learned from compared productions.

Comparisons record what the creator preferred between actual productions and
why. Proposed policies generalize those comparisons; promotion to guidance
takes a human decision against held-out examples. Compiled guidance may rank
candidates and constrain generation — it can never approve its own output.
"""

from .store import (
    TasteError,
    list_comparisons,
    list_policies,
    promote_policy,
    propose_policy,
    record_comparison,
    retire_policy,
    taste_root,
)

__all__ = [
    "TasteError",
    "list_comparisons",
    "list_policies",
    "promote_policy",
    "propose_policy",
    "record_comparison",
    "retire_policy",
    "taste_root",
]
