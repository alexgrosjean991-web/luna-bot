"""
Gates System - Points de frustration stratégiques avant paywall.

Gate 1 (J3): Micro-frustration - "j'aurais voulu te montrer un truc mais..."
Gate 2 (J4): Audio teasé - "j'aimerais t'envoyer un vocal mais..."
Gate 3 (J5): Taste of premium - Luna envoie un "aperçu" qui crée le désir

Chaque gate crée une frustration qui prépare au paywall.
"""

import random
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class GateType(Enum):
    GATE_1 = "gate_1"  # J3 - Micro-frustration
    GATE_2 = "gate_2"  # J4 - Audio teasé
    GATE_3 = "gate_3"  # J5 - Taste of premium


@dataclass
class GateConfig:
    day: int
    probability: float
    hour_range: tuple[int, int]  # (start, end)
    messages: list[str]
    instruction: str


# Configuration des gates
GATES = {
    GateType.GATE_1: GateConfig(
        day=3,
        probability=0.70,
        hour_range=(14, 20),  # Après-midi/soir
        messages=[
            "j'aurais voulu te montrer un truc mais... j'peux pas encore 😅",
            "y'a quelque chose que j'aimerais te montrer mais c'est compliqué ici",
            "j'ai un truc pour toi mais... pas maintenant, pas ici",
            "je voudrais t'envoyer quelque chose mais telegram c'est pas l'idéal",
        ],
        instruction="""## 🚪 GATE 1 - MICRO-FRUSTRATION
Tu veux lui montrer quelque chose mais tu "peux pas encore".
Crée la PREMIÈRE frustration. Il doit sentir qu'il y a PLUS.
Pas d'explication, juste un tease mystérieux.
"""
    ),
    GateType.GATE_2: GateConfig(
        day=4,
        probability=0.75,
        hour_range=(14, 22),
        messages=[
            "j'aimerais tellement t'envoyer un vocal là... 🎙️",
            "si je pouvais te faire écouter ma voix...",
            "j'ai failli t'enregistrer un truc mais c'est pas possible ici",
            "tu voudrais entendre ma voix? 😏 bientôt peut-être...",
        ],
        instruction="""## 🚪 GATE 2 - AUDIO TEASÉ
Tu veux lui envoyer un vocal mais tu "peux pas ici".
Nouvelle feature teasée = nouvelle frustration.
Fais-lui imaginer ta voix sans lui donner.
"""
    ),
    GateType.GATE_3: GateConfig(
        day=5,
        probability=0.80,
        hour_range=(15, 22),
        messages=[
            "oops j'ai failli t'envoyer un truc que j'aurais pas dû 😳",
            "j'ai une photo pour toi mais... la version complète c'est pour après 😏",
            "si tu voyais ce que j'allais t'envoyer... 🙈",
            "j'ai un truc spécial pour toi, bientôt tu verras",
        ],
        instruction="""## 🚪 GATE 3 - TASTE OF PREMIUM
Tu as "failli" lui envoyer quelque chose de spécial.
Il a un APERÇU de ce qu'il rate.
Maximum de frustration avant le paywall demain.
"""
    ),
}


def get_gate_for_day(day_count: int) -> Optional[GateType]:
    """Retourne le type de gate pour ce jour."""
    for gate_type, config in GATES.items():
        if config.day == day_count:
            return gate_type
    return None


def should_trigger_gate(
    day_count: int,
    current_hour: int,
    gate_triggered_today: bool
) -> Optional[GateType]:
    """
    Détermine si on doit déclencher une gate.

    Args:
        day_count: Jour actuel
        current_hour: Heure actuelle
        gate_triggered_today: Si une gate a déjà été triggered aujourd'hui

    Returns:
        GateType à déclencher ou None
    """
    if gate_triggered_today:
        return None

    gate_type = get_gate_for_day(day_count)
    if not gate_type:
        return None

    config = GATES[gate_type]

    # Vérifier l'heure
    start_hour, end_hour = config.hour_range
    if not (start_hour <= current_hour < end_hour):
        return None

    # Probabilité
    if random.random() > config.probability:
        return None

    return gate_type


def get_gate_message(gate_type: GateType) -> str:
    """Retourne un message de gate aléatoire."""
    config = GATES[gate_type]
    return random.choice(config.messages)


def get_gate_instruction(gate_type: GateType) -> str:
    """Retourne l'instruction LLM pour cette gate."""
    config = GATES[gate_type]
    return config.instruction


def check_gate_opportunity(
    day_count: int,
    current_hour: int,
    gates_triggered: list[str]
) -> Optional[tuple[GateType, str]]:
    """
    Vérifie si c'est le moment de déclencher une gate.

    Args:
        day_count: Jour actuel
        current_hour: Heure actuelle
        gates_triggered: Liste des gates déjà déclenchées

    Returns:
        (GateType, message) ou None
    """
    gate_type = get_gate_for_day(day_count)
    if not gate_type:
        return None

    # Vérifier si déjà triggered
    if gate_type.value in gates_triggered:
        return None

    config = GATES[gate_type]

    # Vérifier l'heure
    start_hour, end_hour = config.hour_range
    if not (start_hour <= current_hour < end_hour):
        return None

    # Probabilité
    if random.random() > config.probability:
        return None

    message = random.choice(config.messages)
    logger.info(f"Gate triggered: {gate_type.value} at hour {current_hour}")

    return (gate_type, message)


def get_gates_summary() -> str:
    """Retourne un résumé des gates pour debug."""
    lines = ["Gates Configuration:"]
    for gate_type, config in GATES.items():
        lines.append(
            f"  {gate_type.value}: J{config.day}, "
            f"{config.hour_range[0]}h-{config.hour_range[1]}h, "
            f"prob={config.probability}"
        )
    return "\n".join(lines)
