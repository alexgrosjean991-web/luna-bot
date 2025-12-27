"""
Photo sending for Luna Bot.

Usage:
    from photos import send_photo, PhotoCategory

    result = await send_photo(bot, user_id, PhotoCategory.SELFIE_SFW, phase="CONNECT")
"""

import os
import random
from pathlib import Path
from typing import Optional

from telegram import Bot

from core import get_logger
from config.settings import settings
from photos.access import PhotoCategory, check_access, get_denial_message

logger = get_logger(__name__)


# =============================================================================
# CAPTIONS
# =============================================================================

CAPTIONS = {
    PhotoCategory.PIXEL: [
        "regarde mon bébé",
        "Pixel te dit coucou",
        "il dort encore",
        "trop mignon non?",
    ],
    PhotoCategory.SELFIE_SFW: [
        "tiens",
        "voilà",
        "c'est moi",
        "comme ça tu vois ma tête",
    ],
    PhotoCategory.OUTFIT: [
        "tu aimes?",
        "je sais pas si ça me va",
        "dis-moi ce que t'en penses",
    ],
    PhotoCategory.SUGGESTIVE: [
        "juste pour toi",
        "ça reste entre nous",
        "t'aimes bien?",
    ],
    PhotoCategory.NSFW_SOFT: [
        "rien que pour toi",
        "j'espère que ça te plaît",
        "dis-moi ce que tu veux voir",
    ],
    PhotoCategory.NSFW_EXPLICIT: [
        "voilà ce que tu voulais",
        "juste pour toi bébé",
        "t'es content?",
    ],
}


def get_caption(category: PhotoCategory, user_name: Optional[str] = None) -> str:
    """Get a random caption for the category."""
    captions = CAPTIONS.get(category, ["tiens"])
    caption = random.choice(captions)

    # Personalize if we have the name
    if user_name and random.random() < 0.3:
        caption = f"{caption} {user_name}"

    return caption


# =============================================================================
# PHOTO SELECTION
# =============================================================================

def get_photo_path(category: PhotoCategory) -> Optional[Path]:
    """
    Get a random photo from the category folder.

    Expected folder structure:
    /app/content/photos/
        pixel/
        selfie_sfw/
        outfit/
        suggestive/
        nsfw_soft/
        nsfw_explicit/
    """
    base_path = Path(settings.PHOTOS_PATH)
    category_path = base_path / category.value

    if not category_path.exists():
        logger.warning(f"Photo category folder not found: {category_path}")
        return None

    # Get all images
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    photos = [
        p for p in category_path.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    ]

    if not photos:
        logger.warning(f"No photos in category: {category.value}")
        return None

    return random.choice(photos)


# =============================================================================
# MAIN FUNCTION
# =============================================================================

async def send_photo(
    bot: Bot,
    chat_id: int,
    category: PhotoCategory,
    phase: str,
    trust_score: int = 0,
    nsfw_tier: int = 1,
    is_subscriber: bool = False,
    user_name: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Send a photo to a user if they have access.

    Args:
        bot: Telegram Bot instance
        chat_id: Telegram chat ID
        category: Photo category to send
        phase: Current relationship phase
        trust_score: User's trust score (0-100)
        nsfw_tier: Current NSFW tier (1-3)
        is_subscriber: Is user a paying subscriber
        user_name: User's name for personalization

    Returns:
        (success, message) - message is caption on success, denial on failure
    """
    # Check access
    can_access, denial_reason = check_access(
        category=category,
        phase=phase,
        trust_score=trust_score,
        nsfw_tier=nsfw_tier,
        is_subscriber=is_subscriber,
    )

    if not can_access:
        denial_msg = get_denial_message(denial_reason)
        logger.info(f"Photo denied: {category.value} -> {denial_reason}")
        return False, denial_msg

    # Get photo
    photo_path = get_photo_path(category)
    if not photo_path:
        logger.error(f"No photo available for category: {category.value}")
        return False, "j'ai pas de photo là"

    # Get caption
    caption = get_caption(category, user_name)

    # Send
    try:
        with open(photo_path, "rb") as photo_file:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_file,
                caption=caption,
            )
        logger.info(f"Photo sent: {category.value} -> {chat_id}")
        return True, caption

    except Exception as e:
        logger.error(f"Failed to send photo: {e}")
        return False, "déso j'arrive pas à t'envoyer"


# =============================================================================
# SPONTANEOUS PHOTOS
# =============================================================================

def should_send_spontaneous(
    phase: str,
    mood: str = "normal",
    nsfw_tier: int = 1,
    messages_since_last_photo: int = 0,
) -> Optional[PhotoCategory]:
    """
    Decide if Luna should spontaneously send a photo.

    Returns:
        PhotoCategory to send, or None
    """
    # Base probability: 5%
    base_prob = 0.05

    # Mood bonuses
    mood_bonus = {
        "playful": 0.10,
        "happy": 0.05,
        "vulnerable": 0.03,
    }.get(mood, 0)

    # Tier bonus
    tier_bonus = {1: 0, 2: 0.05, 3: 0.10}.get(nsfw_tier, 0)

    # Messages since last photo bonus (max +10%)
    msg_bonus = min(messages_since_last_photo * 0.01, 0.10)

    total_prob = base_prob + mood_bonus + tier_bonus + msg_bonus

    if random.random() > total_prob:
        return None

    # Decide category based on phase and tier
    if phase in ["HOOK"]:
        return PhotoCategory.PIXEL
    elif phase in ["CONNECT"]:
        return random.choice([PhotoCategory.PIXEL, PhotoCategory.SELFIE_SFW])
    elif phase in ["ATTACH", "TENSION"]:
        if nsfw_tier >= 2:
            return random.choice([PhotoCategory.SELFIE_SFW, PhotoCategory.OUTFIT, PhotoCategory.SUGGESTIVE])
        return random.choice([PhotoCategory.SELFIE_SFW, PhotoCategory.OUTFIT])
    elif phase == "LIBRE":
        if nsfw_tier >= 3:
            return random.choice([PhotoCategory.SUGGESTIVE, PhotoCategory.NSFW_SOFT])
        elif nsfw_tier >= 2:
            return PhotoCategory.SUGGESTIVE
        return random.choice([PhotoCategory.SELFIE_SFW, PhotoCategory.OUTFIT])

    return PhotoCategory.PIXEL
