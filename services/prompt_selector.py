"""
Sélecteur de prompts basé sur le niveau/tier de conversation.
V3: Support for tier-based selection (1=SFW, 2=FLIRT, 3=NSFW).
"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Charger les prompts
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

PROMPT_SFW = (PROMPTS_DIR / "level_sfw.txt").read_text(encoding="utf-8")
PROMPT_TENSION = (PROMPTS_DIR / "level_tension.txt").read_text(encoding="utf-8")
PROMPT_NSFW = (PROMPTS_DIR / "luna_nsfw.txt").read_text(encoding="utf-8")
MODIFIERS = (PROMPTS_DIR / "modifiers.txt").read_text(encoding="utf-8")

# V3: Load flirt prompt (Tier 2)
PROMPT_FLIRT_PATH = PROMPTS_DIR / "level_flirt.txt"
PROMPT_FLIRT = PROMPT_FLIRT_PATH.read_text(encoding="utf-8") if PROMPT_FLIRT_PATH.exists() else PROMPT_TENSION

# Parser les modifiers
MODIFIER_SECTIONS = {}
current_modifier = None
current_content = []

for line in MODIFIERS.split('\n'):
    if line.startswith('### '):
        if current_modifier:
            MODIFIER_SECTIONS[current_modifier] = '\n'.join(current_content)
        current_modifier = line[4:].strip()
        current_content = []
    elif current_modifier:
        current_content.append(line)

if current_modifier:
    MODIFIER_SECTIONS[current_modifier] = '\n'.join(current_content)


def get_prompt_for_level(level: int, modifier: str | None = None) -> str:
    """
    Retourne le prompt approprié pour le niveau de conversation.

    Args:
        level: 1 (SFW), 2 (TENSION), 3 (NSFW)
        modifier: Modificateur optionnel (USER_DISTRESSED, DELAY_GRATIFICATION, etc.)

    Returns:
        Le prompt système complet
    """
    # Sélectionner le prompt de base
    if level == 1:
        base_prompt = PROMPT_SFW
    elif level == 2:
        base_prompt = PROMPT_TENSION
    else:  # level >= 3
        base_prompt = PROMPT_NSFW

    # Ajouter le modifier si présent
    if modifier and modifier in MODIFIER_SECTIONS:
        modifier_text = MODIFIER_SECTIONS[modifier]
        base_prompt = f"{base_prompt}\n\n## ⚠️ INSTRUCTION SPÉCIALE\n{modifier_text}"
        logger.info(f"Prompt modifier applied: {modifier}")

    return base_prompt


def get_level_name(level: int) -> str:
    """Retourne le nom du niveau pour le logging."""
    names = {1: "SFW", 2: "TENSION", 3: "NSFW"}
    return names.get(level, "UNKNOWN")


# ============== V3: Tier-based prompt selection ==============

def get_prompt_for_tier(tier: int, modifier: str | None = None) -> str:
    """
    Retourne le prompt approprié pour le tier de conversation.

    Args:
        tier: 1 (SFW), 2 (FLIRT), 3 (NSFW)
        modifier: Modificateur optionnel

    Returns:
        Le prompt système complet
    """
    # Sélectionner le prompt de base par tier
    if tier == 1:
        base_prompt = PROMPT_SFW
    elif tier == 2:
        base_prompt = PROMPT_FLIRT  # V3: New flirt prompt
    else:  # tier >= 3
        base_prompt = PROMPT_NSFW

    # Ajouter le modifier si présent
    if modifier and modifier in MODIFIER_SECTIONS:
        modifier_text = MODIFIER_SECTIONS[modifier]
        base_prompt = f"{base_prompt}\n\n## ⚠️ INSTRUCTION SPÉCIALE\n{modifier_text}"
        logger.info(f"Prompt modifier applied: {modifier}")

    return base_prompt


def get_tier_name(tier: int) -> str:
    """Retourne le nom du tier pour le logging."""
    names = {1: "SFW", 2: "FLIRT", 3: "NSFW"}
    return names.get(tier, "UNKNOWN")
