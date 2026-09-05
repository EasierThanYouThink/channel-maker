"""Ongoing Episode production: the repeatable content pipeline that runs after a channel
reaches CHANNEL_READY. Deliberately separate from `engine.pilot`, which stays the one-time
proof that Script/Visual/Motion DNA works — episode production never bumps the channel's
version. See the "Ongoing — Episode Production" section of the channel-maker skill.
"""

from .episode import episode_path, plan_episode, record_production, record_review
from .validation import EpisodeValidationError, validate_episode

__all__ = [
    "EpisodeValidationError",
    "episode_path",
    "plan_episode",
    "record_production",
    "record_review",
    "validate_episode",
]
