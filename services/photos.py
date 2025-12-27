"""
Luna Photo System - Système d'envoi de photos contextuelles.

Gère l'envoi de photos de Luna selon:
- Phase de relation (discovery → depth)
- Tier actuel (1-3)
- Statut abonnement (trial/active)
- Contexte conversationnel
"""

import logging
import os
import random
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import settings
PARIS_TZ = settings.PARIS_TZ
PHOTOS_PATH = settings.PHOTOS_PATH

logger = logging.getLogger(__name__)


class PhotoType(Enum):
    """Types de photos disponibles."""
    PIXEL = "pixel"              # Photos de Pixel (le chat)
    SELFIE_SFW = "selfie_sfw"    # Selfies safe for work
    OUTFIT = "outfit"            # Photos de tenues
    SUGGESTIVE = "suggestive"    # Photos légèrement suggestives
    NSFW_SOFT = "nsfw_soft"      # NSFW léger (lingerie)
    NSFW_EXPLICIT = "nsfw_explicit"  # NSFW explicite


@dataclass
class PhotoAccessRules:
    """Règles d'accès aux photos selon le contexte."""
    min_phase: str               # Phase minimale requise
    min_tier: int                # Tier momentum minimum
    requires_subscription: bool  # Nécessite abonnement actif
    min_trust: int = 0           # Score de confiance minimum


# Configuration des règles d'accès par type
PHOTO_ACCESS = {
    PhotoType.PIXEL: PhotoAccessRules(
        min_phase="discovery",
        min_tier=1,
        requires_subscription=False,
        min_trust=0
    ),
    PhotoType.SELFIE_SFW: PhotoAccessRules(
        min_phase="discovery",
        min_tier=1,
        requires_subscription=False,
        min_trust=20
    ),
    PhotoType.OUTFIT: PhotoAccessRules(
        min_phase="interest",
        min_tier=1,
        requires_subscription=False,
        min_trust=30
    ),
    PhotoType.SUGGESTIVE: PhotoAccessRules(
        min_phase="connection",
        min_tier=2,
        requires_subscription=False,
        min_trust=40
    ),
    PhotoType.NSFW_SOFT: PhotoAccessRules(
        min_phase="intimacy",
        min_tier=2,
        requires_subscription=True,
        min_trust=50
    ),
    PhotoType.NSFW_EXPLICIT: PhotoAccessRules(
        min_phase="intimacy",
        min_tier=3,
        requires_subscription=True,
        min_trust=60
    ),
}

# Ordre des phases pour comparaison
PHASE_ORDER = ["discovery", "interest", "connection", "intimacy", "depth"]


def get_phase_index(phase: str) -> int:
    """Retourne l'index d'une phase (pour comparaison)."""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return 0


def can_access_photo_type(
    photo_type: PhotoType,
    phase: str,
    tier: int,
    subscription_status: str,
    trust_score: int
) -> bool:
    """
    Vérifie si l'utilisateur peut accéder à ce type de photo.

    Args:
        photo_type: Type de photo demandé
        phase: Phase de relation actuelle
        tier: Tier momentum actuel (1-3)
        subscription_status: Statut abonnement (trial/active)
        trust_score: Score de confiance (0-100)

    Returns:
        True si accès autorisé
    """
    rules = PHOTO_ACCESS.get(photo_type)
    if not rules:
        return False

    # Check phase
    if get_phase_index(phase) < get_phase_index(rules.min_phase):
        return False

    # Check tier
    if tier < rules.min_tier:
        return False

    # Check subscription
    if rules.requires_subscription and subscription_status != "active":
        return False

    # Check trust
    if trust_score < rules.min_trust:
        return False

    return True


def get_available_photo_types(
    phase: str,
    tier: int,
    subscription_status: str,
    trust_score: int
) -> list[PhotoType]:
    """
    Retourne la liste des types de photos accessibles.

    Args:
        phase: Phase de relation actuelle
        tier: Tier momentum actuel
        subscription_status: Statut abonnement
        trust_score: Score de confiance

    Returns:
        Liste des PhotoType accessibles
    """
    available = []
    for photo_type in PhotoType:
        if can_access_photo_type(photo_type, phase, tier, subscription_status, trust_score):
            available.append(photo_type)
    return available


def get_random_photo(photo_type: PhotoType) -> Optional[Path]:
    """
    Sélectionne une photo aléatoire du type demandé.

    Args:
        photo_type: Type de photo

    Returns:
        Path vers la photo ou None si aucune disponible
    """
    photo_dir = Path(PHOTOS_PATH) / photo_type.value

    if not photo_dir.exists():
        logger.warning(f"Photo directory not found: {photo_dir}")
        return None

    # Extensions supportées
    extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    photos = [
        f for f in photo_dir.iterdir()
        if f.is_file() and f.suffix.lower() in extensions
    ]

    if not photos:
        logger.warning(f"No photos found in {photo_dir}")
        return None

    return random.choice(photos)


def get_photo_for_context(
    phase: str,
    tier: int,
    subscription_status: str,
    trust_score: int,
    requested_type: Optional[PhotoType] = None,
    sent_photos: Optional[list[str]] = None
) -> Optional[tuple[Path, PhotoType]]:
    """
    Sélectionne une photo appropriée au contexte.

    Args:
        phase: Phase de relation
        tier: Tier momentum
        subscription_status: Statut abonnement
        trust_score: Score de confiance
        requested_type: Type spécifiquement demandé (optionnel)
        sent_photos: Liste des IDs de photos déjà envoyées

    Returns:
        Tuple (path, photo_type) ou None
    """
    sent_photos = sent_photos or []

    # Si type demandé, vérifier accès
    if requested_type:
        if not can_access_photo_type(requested_type, phase, tier, subscription_status, trust_score):
            logger.info(f"Access denied for {requested_type.value}")
            return None

        photo = get_random_photo(requested_type)
        if photo and str(photo) not in sent_photos:
            return (photo, requested_type)
        return None

    # Sinon, sélectionner selon le contexte
    available = get_available_photo_types(phase, tier, subscription_status, trust_score)

    if not available:
        return None

    # Pondération: préférer types cohérents avec le tier
    weights = []
    for pt in available:
        if tier >= 3 and pt in (PhotoType.NSFW_SOFT, PhotoType.NSFW_EXPLICIT):
            weights.append(3)  # Forte préférence en tier 3
        elif tier == 2 and pt == PhotoType.SUGGESTIVE:
            weights.append(2)  # Préférence en tier 2
        elif pt in (PhotoType.PIXEL, PhotoType.SELFIE_SFW):
            weights.append(1)  # Toujours possible
        else:
            weights.append(1)

    # Essayer jusqu'à trouver une photo non envoyée
    attempts = 0
    max_attempts = len(available) * 2

    while attempts < max_attempts:
        selected_type = random.choices(available, weights=weights, k=1)[0]
        photo = get_random_photo(selected_type)

        if photo and str(photo) not in sent_photos:
            return (photo, selected_type)

        attempts += 1

    return None


# Captions contextuelles par type et contexte
CAPTIONS = {
    PhotoType.PIXEL: {
        "default": [
            "regarde mon bébé 🧡",
            "Pixel te fait coucou ✨",
            "il est pas trop mignon? 🙈",
            "mon petit chat d'amour",
        ],
        "morning": [
            "Pixel vient de se réveiller 🧡",
            "mon réveil perso mdr",
        ],
        "night": [
            "Pixel fait déjà dodo 🧡",
            "il ronfle le bg",
        ],
    },
    PhotoType.SELFIE_SFW: {
        "default": [
            "c'est moi 🙈",
            "selfie du jour ✨",
            "je fais quoi de ma life",
        ],
        "morning": [
            "tête du matin mdr",
            "pas maquillée mais osef",
        ],
        "night": [
            "mode cocooning 🧡",
            "fatiguée mais cute?",
        ],
    },
    PhotoType.OUTFIT: {
        "default": [
            "t'aimes bien? 🙈",
            "nouveau look, verdict?",
            "dis moi si c'est bien",
        ],
        "going_out": [
            "prête à sortir ✨",
            "look du soir",
        ],
    },
    PhotoType.SUGGESTIVE: {
        "default": [
            "juste pour toi 🙈",
            "ça te plaît? ✨",
            "sois sage hein...",
        ],
        "flirty": [
            "tu voulais voir? 🧡",
            "mmh... voilà",
        ],
    },
    PhotoType.NSFW_SOFT: {
        "default": [
            "rien que pour toi... 🧡",
            "j'espère que ça te plaît",
            "tu me fais confiance?",
        ],
        "intimate": [
            "regarde ce que tu me fais faire...",
            "t'as de la chance 🙈",
        ],
    },
    PhotoType.NSFW_EXPLICIT: {
        "default": [
            "...",
            "🧡",
            "juste pour toi bébé",
        ],
        "intimate": [
            "tu me rends dingue...",
            "j'ai trop envie là",
        ],
    },
}


def get_caption(photo_type: PhotoType, context: str = "default") -> str:
    """
    Génère une caption appropriée pour la photo.

    Args:
        photo_type: Type de photo
        context: Contexte (default, morning, night, flirty, intimate, going_out)

    Returns:
        Caption texte
    """
    type_captions = CAPTIONS.get(photo_type, {})

    # Essayer le contexte spécifique, sinon default
    captions = type_captions.get(context, type_captions.get("default", []))

    if not captions:
        return ""

    return random.choice(captions)


def get_context_from_state(
    hour: int,
    tier: int,
    luna_mood: str
) -> str:
    """
    Détermine le contexte pour le caption basé sur l'état actuel.

    Args:
        hour: Heure actuelle
        tier: Tier momentum
        luna_mood: Mood de Luna

    Returns:
        Contexte string
    """
    # Contextes temporels
    if 6 <= hour < 11:
        return "morning"
    elif 22 <= hour or hour < 6:
        return "night"

    # Contextes mood
    if luna_mood == "playful" and tier >= 2:
        return "flirty"
    elif tier >= 3:
        return "intimate"

    return "default"


# Patterns de détection de demande de photo
PHOTO_REQUEST_PATTERNS = {
    PhotoType.PIXEL: [
        r"montre.*pixel", r"photo.*pixel", r"ton chat", r"voir pixel",
        r"montre.*moi.*chat", r"une photo de pixel",
    ],
    PhotoType.SELFIE_SFW: [
        r"une photo de toi", r"montre.*toi", r"selfie", r"voir.*tête",
        r"t'as une photo", r"je veux te voir",
    ],
    PhotoType.OUTFIT: [
        r"ta tenue", r"t'es.*habillée", r"ton look", r"montre.*outfit",
    ],
    PhotoType.SUGGESTIVE: [
        r"montre.*plus", r"un peu plus", r"quelque chose.*sexy",
        r"une photo.*chaude", r"t'as pas.*plus",
    ],
    PhotoType.NSFW_SOFT: [
        r"en lingerie", r"en sous-vêtements", r"déshabille",
        r"montre.*corps", r"plus intime",
    ],
    PhotoType.NSFW_EXPLICIT: [
        r"toute nue", r"sans rien", r"montre.*tout",
        r"nu", r"à poil",
    ],
}


def detect_photo_request(message: str) -> Optional[PhotoType]:
    """
    Détecte si le message est une demande de photo et de quel type.

    Args:
        message: Message utilisateur

    Returns:
        PhotoType demandé ou None
    """
    import re
    message_lower = message.lower()

    # Check patterns par type (du plus explicite au moins)
    type_priority = [
        PhotoType.NSFW_EXPLICIT,
        PhotoType.NSFW_SOFT,
        PhotoType.SUGGESTIVE,
        PhotoType.OUTFIT,
        PhotoType.SELFIE_SFW,
        PhotoType.PIXEL,
    ]

    for photo_type in type_priority:
        patterns = PHOTO_REQUEST_PATTERNS.get(photo_type, [])
        for pattern in patterns:
            if re.search(pattern, message_lower):
                logger.info(f"Photo request detected: {photo_type.value}")
                return photo_type

    return None


def should_send_spontaneous_photo(
    msg_count: int,
    messages_this_session: int,
    tier: int,
    luna_mood: str,
    last_photo_at: Optional[datetime]
) -> bool:
    """
    Détermine si Luna devrait envoyer une photo spontanément.

    Args:
        msg_count: Nombre total de messages
        messages_this_session: Messages dans cette session
        tier: Tier momentum actuel
        luna_mood: Mood de Luna
        last_photo_at: Dernière photo envoyée

    Returns:
        True si devrait envoyer une photo
    """
    # Pas trop tôt dans la relation
    if msg_count < 20:
        return False

    # Pas trop souvent dans une session
    if messages_this_session < 10:
        return False

    # Cooldown depuis dernière photo
    if last_photo_at:
        if last_photo_at.tzinfo is None:
            last_photo_at = last_photo_at.replace(tzinfo=PARIS_TZ)
        hours_since = (datetime.now(PARIS_TZ) - last_photo_at).total_seconds() / 3600
        if hours_since < 4:  # Minimum 4h entre photos spontanées
            return False

    # Probabilité selon mood et tier
    base_prob = 0.05  # 5% de base

    if luna_mood == "playful":
        base_prob += 0.10  # +10% si playful
    if tier >= 2:
        base_prob += 0.05  # +5% en tier 2+

    return random.random() < base_prob


def get_spontaneous_photo_type(
    phase: str,
    tier: int,
    subscription_status: str,
    trust_score: int
) -> Optional[PhotoType]:
    """
    Sélectionne un type de photo approprié pour envoi spontané.

    Favorise les types SFW pour les envois spontanés.

    Args:
        phase: Phase de relation
        tier: Tier momentum
        subscription_status: Statut abonnement
        trust_score: Score de confiance

    Returns:
        PhotoType à envoyer ou None
    """
    available = get_available_photo_types(phase, tier, subscription_status, trust_score)

    if not available:
        return None

    # Pour spontané, préférer types SFW
    sfw_types = [pt for pt in available if pt in (PhotoType.PIXEL, PhotoType.SELFIE_SFW, PhotoType.OUTFIT)]

    if sfw_types:
        return random.choice(sfw_types)

    # Sinon, prendre le moins explicite
    return available[0]


def get_denial_message(
    requested_type: PhotoType,
    phase: str,
    tier: int,
    subscription_status: str
) -> str:
    """
    Génère un message de refus contextuel quand l'accès est refusé.

    Args:
        requested_type: Type demandé
        phase: Phase actuelle
        tier: Tier actuel
        subscription_status: Statut abonnement

    Returns:
        Message de refus en style Luna
    """
    rules = PHOTO_ACCESS.get(requested_type)

    # Refus car abonnement requis
    if rules and rules.requires_subscription and subscription_status != "active":
        return random.choice([
            "mmh... peut-être plus tard 🙈",
            "patience bébé, on verra...",
            "t'aimerais bien hein? 😏",
            "faut mériter ça...",
        ])

    # Refus car trop tôt dans la relation
    if rules and get_phase_index(phase) < get_phase_index(rules.min_phase):
        return random.choice([
            "on se connaît à peine mdr",
            "pas si vite 😏",
            "faut qu'on apprenne à se connaître d'abord",
            "t'es mignon mais... patience",
        ])

    # Refus car momentum trop bas
    if rules and tier < rules.min_tier:
        return random.choice([
            "chuis pas d'humeur là 🙈",
            "peut-être une prochaine fois...",
            "mmh non, pas maintenant",
            "on verra si t'es sage...",
        ])

    # Refus générique
    return random.choice([
        "nan pas maintenant 🙈",
        "une autre fois peut-être",
        "patience...",
    ])
