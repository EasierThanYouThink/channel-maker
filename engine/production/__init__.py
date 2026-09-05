"""Shared production-completeness gate for pilots and episodes.

"Approved" must mean a real, exact production: a script file, narration
audio, at least one scene manifest plus one evaluation result (both with
verified hashes), and a non-empty render file. Anything less cannot stand
in for success at review, freeze, or readiness time.
"""

from .completeness import ProductionIncompleteError, check_production, require_complete

__all__ = [
    "ProductionIncompleteError",
    "check_production",
    "require_complete",
]
