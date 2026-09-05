"""Channel identity: a logo and an About-page description, synthesized from the channel's
already-frozen Foundation, Script DNA, and Visual DNA. See docs/CHANNEL_IDENTITY.md.
"""

from .seed import add_reference, all_domains_frozen, freeze_domain, identity_path, init_identity
from .store import ChannelIdentityStore
from .validation import (
    IdentityValidationError,
    resolve_domain_references,
    validate_channel_identity,
    validate_identity_candidate,
    validate_identity_candidate_review,
)

__all__ = [
    "ChannelIdentityStore",
    "IdentityValidationError",
    "add_reference",
    "all_domains_frozen",
    "freeze_domain",
    "identity_path",
    "init_identity",
    "resolve_domain_references",
    "validate_channel_identity",
    "validate_identity_candidate",
    "validate_identity_candidate_review",
]
