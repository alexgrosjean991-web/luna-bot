"""Config module for Luna Bot."""

from .luna import (
    LUNA_IDENTITY,
    LUNA_ABSOLUTE_RULES,
    LUNA_BANNED_PATTERNS,
    LUNA_LAYERS,
    NSFW_TIERS,
    PROACTIVE_CONFIG,
    LUNA_POST_PAYWALL_PROMPT,
    NSFW_REQUEST_KEYWORDS,
    CLIMAX_INDICATORS,
    get_available_layers,
    get_nsfw_tier,
    build_system_prompt,
)

__all__ = [
    "LUNA_IDENTITY",
    "LUNA_ABSOLUTE_RULES",
    "LUNA_BANNED_PATTERNS",
    "LUNA_LAYERS",
    "NSFW_TIERS",
    "PROACTIVE_CONFIG",
    "LUNA_POST_PAYWALL_PROMPT",
    "NSFW_REQUEST_KEYWORDS",
    "CLIMAX_INDICATORS",
    "get_available_layers",
    "get_nsfw_tier",
    "build_system_prompt",
]
