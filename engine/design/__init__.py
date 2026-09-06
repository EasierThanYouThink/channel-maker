"""Channel-scoped Visual/Motion DNA discovery: exemplar-driven identity across five
visual domains and one motion domain. See docs/CHANNEL_DESIGN_DNA.md.
"""

from .dna_seed import (
    add_reference,
    all_domains_frozen,
    freeze_domain,
    init_seed,
    seed_path,
)
from .exemplars import ChannelExemplarStore
from .system_proof import (
    approved_composition,
    approved_motion_sample,
    check_ready_problems,
    composition_path,
    motion_sample_path,
    record_composition,
    record_motion_sample,
    review_composition,
    review_motion_sample,
)
from .validation import (
    DesignValidationError,
    resolve_domain_references,
    validate_dna_seed,
    validate_exemplar,
    validate_exemplar_review,
)

__all__ = [
    "ChannelExemplarStore",
    "DesignValidationError",
    "add_reference",
    "all_domains_frozen",
    "approved_composition",
    "approved_motion_sample",
    "check_ready_problems",
    "composition_path",
    "freeze_domain",
    "init_seed",
    "motion_sample_path",
    "record_composition",
    "record_motion_sample",
    "resolve_domain_references",
    "review_composition",
    "review_motion_sample",
    "seed_path",
    "validate_dna_seed",
    "validate_exemplar",
    "validate_exemplar_review",
]
