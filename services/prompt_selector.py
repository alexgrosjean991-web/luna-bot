"""
Sélecteur de prompts basé sur le niveau/tier de conversation.
V3: Support for tier-based selection (1=SFW, 2=FLIRT, 3=NSFW).
V7: Support for NSFW states (tension, buildup, climax, aftercare).
"""

from pathlib import Path
import logging
import sys

logger = logging.getLogger(__name__)

# Import des prompts NSFW V7
sys.path.insert(0, str(Path(__file__).parent.parent / "prompts"))
from nsfw_prompts import NSFW_PROMPTS, format_nsfw_prompt

# Charger les prompts
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

PROMPT_SFW = (PROMPTS_DIR / "level_sfw.txt").read_text(encoding="utf-8")
PROMPT_FLIRT = (PROMPTS_DIR / "level_flirt.txt").read_text(encoding="utf-8")
PROMPT_NSFW = (PROMPTS_DIR / "luna_nsfw.txt").read_text(encoding="utf-8")
MODIFIERS = (PROMPTS_DIR / "modifiers.txt").read_text(encoding="utf-8")

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


# ============== V7: NSFW state-based prompt selection ==============

def get_nsfw_prompt_v7(
    nsfw_state: str,
    user_name: str = "lui",
    inside_jokes: list | None = None,
    pet_names: list | None = None,
    modifier: str | None = None
) -> str:
    """
    Retourne le prompt NSFW V7 approprié pour l'état donné.

    Args:
        nsfw_state: 'tension', 'buildup', 'climax', 'aftercare'
        user_name: Prénom de l'utilisateur
        inside_jokes: Liste des inside jokes
        pet_names: Liste des petits noms
        modifier: Modificateur optionnel

    Returns:
        Le prompt système complet
    """
    # Get base prompt from NSFW_PROMPTS
    base_prompt = format_nsfw_prompt(
        state=nsfw_state,
        user_name=user_name,
        inside_jokes=inside_jokes,
        pet_names=pet_names
    )

    # Add modifier if present
    if modifier and modifier in MODIFIER_SECTIONS:
        modifier_text = MODIFIER_SECTIONS[modifier]
        base_prompt = f"{base_prompt}\n\n## INSTRUCTION SPÉCIALE\n{modifier_text}"
        logger.info(f"NSFW prompt modifier applied: {modifier}")

    logger.info(f"Using NSFW V7 prompt: state={nsfw_state}, user={user_name}")
    return base_prompt


def get_prompt_for_tier_v7(
    tier: int,
    nsfw_state: str = 'tension',
    user_name: str = "lui",
    inside_jokes: list | None = None,
    pet_names: list | None = None,
    modifier: str | None = None
) -> str:
    """
    V7: Retourne le prompt approprié avec support NSFW états.

    Args:
        tier: 1 (SFW), 2 (FLIRT), 3 (NSFW)
        nsfw_state: Pour tier 3: 'tension', 'buildup', 'climax', 'aftercare'
        user_name: Prénom de l'utilisateur
        inside_jokes: Liste des inside jokes
        pet_names: Liste des petits noms
        modifier: Modificateur optionnel

    Returns:
        Le prompt système complet
    """
    # Tier 1: SFW
    if tier == 1:
        base_prompt = PROMPT_SFW
        if modifier and modifier in MODIFIER_SECTIONS:
            base_prompt = f"{base_prompt}\n\n## INSTRUCTION SPÉCIALE\n{MODIFIER_SECTIONS[modifier]}"
        return base_prompt

    # Tier 2: FLIRT
    if tier == 2:
        base_prompt = PROMPT_FLIRT
        if modifier and modifier in MODIFIER_SECTIONS:
            base_prompt = f"{base_prompt}\n\n## INSTRUCTION SPÉCIALE\n{MODIFIER_SECTIONS[modifier]}"
        return base_prompt

    # Tier 3: NSFW avec états V7
    return get_nsfw_prompt_v7(
        nsfw_state=nsfw_state,
        user_name=user_name,
        inside_jokes=inside_jokes,
        pet_names=pet_names,
        modifier=modifier
    )
