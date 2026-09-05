"""Channel-scoped Visual/Motion DNA discovery: exemplar-driven identity across five
visual domains and one motion domain. See docs/CHANNEL_DESIGN_DNA.md.
"""

from .dna_seed import add_reference, all_domains_frozen, freeze_domain, init_seed, seed_path
from .exemplars import ChannelExemplarStore
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
    "freeze_domain",
    "init_seed",
    "resolve_domain_references",
    "seed_path",
    "validate_dna_seed",
    "validate_exemplar",
    "validate_exemplar_review",
]
