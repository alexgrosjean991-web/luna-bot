"""
LLM Router V3 - Three-Tier Momentum-Based Routing.

Routes to optimal model based on momentum:
    - Tier 1 (momentum 0-30): Haiku SFW
    - Tier 2 (momentum 31-60): Magnum Flirt
    - Tier 3 (momentum 61+): Magnum NSFW

Override rules:
    - NSFW detected in message → always Magnum
    - Active subscriber → always Magnum
    - AFTERCARE/POST_INTIMATE modifier → Magnum (history context)
"""

import logging
from services.momentum import momentum_engine, Intensity

logger = logging.getLogger(__name__)

# Model configurations
HAIKU_CONFIG = ("anthropic", "claude-haiku-4-5-20251001")
MAGNUM_CONFIG = ("openrouter", "anthracite-org/magnum-v4-72b")

# Tier to prompt mapping
TIER_PROMPTS = {
    1: "level_sfw.txt",
    2: "level_flirt.txt",
    3: "luna_nsfw.txt",
}


def get_tier(
    momentum: float,
    day_count: int,
    intimacy_history: int
) -> int:
    """
    Determine tier based on momentum and user history.

    Thresholds adapt to intimacy_history:
    - New user (0 sessions): higher thresholds (40, 70)
    - Some history (1-2): normal thresholds (35, 60)
    - Regular (3-9): lower thresholds (25, 50)
    - Intimate (10+): lowest thresholds (20, 40)
    """
    # Get adaptive thresholds
    tier2, tier3 = momentum_engine.get_tier_thresholds(intimacy_history)

    if momentum >= tier3:
        return 3
    elif momentum >= tier2:
        return 2
    return 1


def get_llm_config_v3(
    momentum: float,
    day_count: int,
    intimacy_history: int,
    subscription_status: str,
    detected_intensity: Intensity,
    modifier: str | None = None
) -> tuple[str, str, int]:
    """
    Returns (provider, model, tier) based on intensity and context.

    Routing by INTENSITY (not momentum):
    1. NSFW → Magnum Tier 3
    2. HOT → Magnum Tier 2
    3. FLIRT → Magnum Tier 2
    4. SFW → Haiku Tier 1 (except during recovery)

    Recovery modifiers override to Magnum (needs NSFW context).
    """
    # Override 1: Recovery modifiers need Magnum (NSFW history context)
    if modifier in ("AFTERCARE", "POST_INTIMATE", "POST_NSFW"):
        tier = 2 if modifier == "POST_INTIMATE" else 2
        logger.info(f"Router: Magnum Tier {tier} ({modifier} modifier)")
        return (*MAGNUM_CONFIG, tier)

    # Route by detected intensity
    if detected_intensity == Intensity.NSFW:
        logger.info(f"Router: Magnum Tier 3 (NSFW detected)")
        return (*MAGNUM_CONFIG, 3)

    if detected_intensity == Intensity.HOT:
        logger.info(f"Router: Magnum Tier 2 (HOT detected)")
        return (*MAGNUM_CONFIG, 2)

    if detected_intensity == Intensity.FLIRT:
        logger.info(f"Router: Magnum Tier 2 (FLIRT detected)")
        return (*MAGNUM_CONFIG, 2)

    # SFW → Haiku (cost optimization)
    logger.info(f"Router: Haiku Tier 1 (SFW, momentum={momentum:.1f})")
    return (*HAIKU_CONFIG, 1)


def get_prompt_file_for_tier(tier: int) -> str:
    """Returns the prompt filename for a given tier."""
    return TIER_PROMPTS.get(tier, "level_sfw.txt")


def is_premium_session(provider: str) -> bool:
    """Check if using premium model (OpenRouter)."""
    return provider == "openrouter"


# ============== LEGACY COMPATIBILITY ==============
# Keep old function signature for gradual migration

def get_llm_config(
    day_count: int,
    teasing_stage: int,
    subscription_status: str,
    hour: int | None = None,
    current_level: int = 1,
    level_modifier: str | None = None,
    detected_level: int = 1
) -> tuple[str, str]:
    """
    LEGACY: Old V7 interface, now wraps V3.

    Maps old level-based system to new momentum-based:
    - Level 1 → Tier 1
    - Level 2 → Tier 2
    - Level 3 → Tier 3
    """
    # Approximate momentum from level
    level_to_momentum = {1: 15, 2: 45, 3: 75}
    momentum = level_to_momentum.get(detected_level, 15)

    # Map intensity
    intensity = Intensity.SFW
    if detected_level >= 3:
        intensity = Intensity.NSFW
    elif detected_level == 2:
        intensity = Intensity.HOT

    provider, model, _ = get_llm_config_v3(
        momentum=momentum,
        day_count=day_count,
        intimacy_history=0,  # Legacy doesn't track this
        subscription_status=subscription_status,
        detected_intensity=intensity,
        modifier=level_modifier
    )

    return (provider, model)
