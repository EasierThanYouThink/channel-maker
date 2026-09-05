"""Structured human decision records: what was chosen, what was declined, and when to revisit.

A decision reference has always been "a real file". Records marked with a
``decision_record`` frontmatter block additionally carry a checkable shape:
the selected options, the rejected alternative, and the revisit condition.
Unmarked files keep working (backward compatibility), but the skill teaches
marked records on every human gate so approvals record decisions, not labels.
"""

from .records import DecisionError, validate_record_file, write_record

__all__ = [
    "DecisionError",
    "validate_record_file",
    "write_record",
]
