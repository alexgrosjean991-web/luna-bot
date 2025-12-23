"""
Human Behavior Simulation
Fait agir Luna comme une vraie personne.
"""

import asyncio
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class BehaviorType(Enum):
    INSTANT = "instant"           # Répond direct
    DELAYED = "delayed"           # Répond après un délai
    SEEN_NO_REPLY = "seen"        # Vu mais pas répondu tout de suite
    TYPING_ABANDON = "abandon"    # Commence à écrire puis arrête
    BUSY = "busy"                 # Occupée, répondra plus tard


@dataclass
class BehaviorResult:
    behavior: BehaviorType
    initial_delay: float          # Délai avant de commencer à répondre
    show_typing_then_stop: bool   # Montrer typing puis arrêter
    excuse_message: Optional[str] # Message d'excuse si delayed
    life_event: Optional[str]     # Ce qu'elle faisait


# Life events par période de la journée
LIFE_EVENTS = {
    # Matin (7-11h)
    "morning": [
        {"event": "douche", "delay_range": (120, 300), "excuse": "dsl j'étais sous la douche"},
        {"event": "café", "delay_range": (30, 120), "excuse": "attendais mon café mdr"},
        {"event": "réveil", "delay_range": (60, 180), "excuse": "j'émerge à peine"},
        {"event": "routine", "delay_range": (60, 240), "excuse": "j'me préparais"},
    ],
    # Midi (11-14h)
    "lunch": [
        {"event": "repas", "delay_range": (300, 900), "excuse": "j'mangeais"},
        {"event": "pause", "delay_range": (120, 300), "excuse": "pause dej"},
        {"event": "café collègues", "delay_range": (180, 420), "excuse": "j'étais avec des collègues"},
    ],
    # Après-midi (14-18h)
    "afternoon": [
        {"event": "taf", "delay_range": (60, 300), "excuse": "dsl le taf"},
        {"event": "réunion", "delay_range": (600, 1800), "excuse": "j'étais en réunion"},
        {"event": "concentrée", "delay_range": (120, 480), "excuse": "j'étais focus sur un truc"},
    ],
    # Soir (18-22h)
    "evening": [
        {"event": "sport", "delay_range": (1800, 3600), "excuse": "j'étais au sport"},
        {"event": "douche", "delay_range": (300, 600), "excuse": "j'étais sous la douche 🚿"},
        {"event": "série", "delay_range": (300, 900), "excuse": "dsl j'étais captivée par ma série"},
        {"event": "cuisine", "delay_range": (300, 600), "excuse": "je faisais à manger"},
        {"event": "Léa", "delay_range": (300, 900), "excuse": "je parlais avec Léa"},
    ],
    # Nuit (22-7h)
    "night": [
        {"event": "dodo", "delay_range": (1800, 7200), "excuse": "je dormais"},
        {"event": "film", "delay_range": (600, 1200), "excuse": "je matais un film"},
        {"event": "fatiguée", "delay_range": (120, 300), "excuse": "dsl j'étais dans les vapes"},
        {"event": "lit", "delay_range": (60, 180), "excuse": "j'étais au lit avec mon tel"},
    ],
}


class HumanBehavior:
    """
    Simule des comportements humains réalistes.
    """

    # TEST MODE: Set to True for instant responses (debugging)
    TEST_MODE = True  # TODO: Set to False in production

    def __init__(self):
        self._last_behaviors: Dict[int, Tuple[datetime, BehaviorType]] = {}
        self._pending_replies: Dict[int, datetime] = {}  # user_id -> when to reply

    def get_time_period(self, hour: int) -> str:
        """Get current time period"""
        if 7 <= hour < 11:
            return "morning"
        elif 11 <= hour < 14:
            return "lunch"
        elif 14 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"

    def decide_behavior(
        self,
        user_id: int,
        affection: float,
        hour: int,
        message_length: int,
        is_nsfw: bool,
        messages_today: int
    ) -> BehaviorResult:
        """
        Décide du comportement de Luna pour ce message.
        """
        # TEST MODE: Always instant response for debugging
        if self.TEST_MODE:
            return BehaviorResult(
                behavior=BehaviorType.INSTANT,
                initial_delay=random.uniform(0.5, 1.5),
                show_typing_then_stop=False,
                excuse_message=None,
                life_event=None
            )

        period = self.get_time_period(hour)

        # === INSTANT RESPONSES ===
        # NSFW: toujours rapide (elle est engagée)
        if is_nsfw:
            return BehaviorResult(
                behavior=BehaviorType.INSTANT,
                initial_delay=random.uniform(1, 5),
                show_typing_then_stop=False,
                excuse_message=None,
                life_event=None
            )

        # Affection haute + premier message du jour: elle attendait
        if affection > 60 and messages_today <= 1:
            return BehaviorResult(
                behavior=BehaviorType.INSTANT,
                initial_delay=random.uniform(2, 10),
                show_typing_then_stop=False,
                excuse_message=None,
                life_event=None
            )

        # === DELAYED RESPONSES ===
        # Chance de délai basée sur l'heure et l'affection
        delay_chance = self._calculate_delay_chance(hour, affection, messages_today)

        if random.random() < delay_chance:
            return self._create_delayed_behavior(period, affection)

        # === TYPING THEN ABANDON (rare) ===
        if random.random() < 0.05 and affection > 30:  # 5% chance
            return BehaviorResult(
                behavior=BehaviorType.TYPING_ABANDON,
                initial_delay=random.uniform(5, 15),
                show_typing_then_stop=True,
                excuse_message=None,
                life_event="distracted"
            )

        # === SEEN NO REPLY (puis répond plus tard) ===
        if random.random() < 0.08:  # 8% chance
            return self._create_seen_no_reply(period)

        # === DEFAULT: Réponse normale avec petit délai ===
        return BehaviorResult(
            behavior=BehaviorType.INSTANT,
            initial_delay=random.uniform(3, 15),
            show_typing_then_stop=False,
            excuse_message=None,
            life_event=None
        )

    def _calculate_delay_chance(self, hour: int, affection: float, messages_today: int) -> float:
        """Calcule la probabilité d'un délai"""
        base_chance = 0.15

        # Plus de chance de délai pendant les heures de travail
        if 9 <= hour <= 17:
            base_chance += 0.10

        # Moins de délai si elle l'aime beaucoup
        if affection > 70:
            base_chance -= 0.08
        elif affection < 30:
            base_chance += 0.10

        # Plus de délais après plusieurs messages (fatigue)
        if messages_today > 20:
            base_chance += 0.15

        return max(0.05, min(0.40, base_chance))

    def _create_delayed_behavior(self, period: str, affection: float) -> BehaviorResult:
        """Crée un comportement avec délai"""
        events = LIFE_EVENTS.get(period, LIFE_EVENTS["afternoon"])
        event = random.choice(events)

        delay_min, delay_max = event["delay_range"]
        # Réduire le délai si affection haute
        if affection > 60:
            delay_min = int(delay_min * 0.5)
            delay_max = int(delay_max * 0.5)

        delay = random.uniform(delay_min, delay_max)

        return BehaviorResult(
            behavior=BehaviorType.DELAYED,
            initial_delay=delay,
            show_typing_then_stop=False,
            excuse_message=event["excuse"],
            life_event=event["event"]
        )

    def _create_seen_no_reply(self, period: str) -> BehaviorResult:
        """Crée un comportement 'vu mais pas répondu'"""
        events = LIFE_EVENTS.get(period, LIFE_EVENTS["afternoon"])
        event = random.choice(events)

        # Délai plus court que delayed normal
        delay = random.uniform(60, 300)

        excuses = [
            "pardon j'avais vu mais j'ai oublié de répondre",
            "oops j'ai vu ton msg et après j'ai zappé",
            "dsl j'étais distraite",
            "my bad j'avais lu vite",
        ]

        return BehaviorResult(
            behavior=BehaviorType.SEEN_NO_REPLY,
            initial_delay=delay,
            show_typing_then_stop=False,
            excuse_message=random.choice(excuses),
            life_event=event["event"]
        )

    def should_forget_detail(self, affection: float) -> Tuple[bool, Optional[str]]:
        """
        Parfois Luna oublie un détail (réaliste).
        Retourne (should_forget, excuse)
        """
        # Plus elle l'aime, moins elle oublie
        forget_chance = 0.08 if affection > 50 else 0.15

        if random.random() < forget_chance:
            excuses = [
                "ah oui t'avais dit! dsl j'avais zappé",
                "ah merde oui c'est vrai",
                "oups j'avais oublié",
                "ah ouais maintenant que tu le dis",
            ]
            return True, random.choice(excuses)

        return False, None

    def get_random_life_update(self, hour: int, affection: float) -> Optional[str]:
        """
        Génère une mise à jour aléatoire sur sa vie.
        Pour les messages proactifs ou ajouts naturels.
        """
        period = self.get_time_period(hour)

        updates = {
            "morning": [
                "Caramel m'a réveillée en me marchant sur la tête",
                "j'ai trop mal dormi",
                "mon café est trop bon ce matin",
                "j'ai pas envie d'aller bosser",
            ],
            "lunch": [
                "j'ai trop bien mangé",
                "y'a un mec relou au taf",
                "vivement ce soir",
                "j'ai faim en fait",
            ],
            "afternoon": [
                "c'est long aujourd'hui",
                "j'attends que ça finisse",
                "j'ai envie d'un café",
                "Léa m'a envoyé un truc trop drôle",
            ],
            "evening": [
                "jsuis crevée",
                "Caramel fait ses trucs de fou",
                "je sais pas quoi manger",
                "j'hésite à mater un truc",
            ],
            "night": [
                "j'arrive pas à dormir",
                "je scroll au lieu de dormir",
                "Caramel dort sur moi",
                "je pense trop",
            ],
        }

        if random.random() < 0.12:  # 12% chance
            return random.choice(updates.get(period, updates["afternoon"]))

        return None


# Instance globale
human_behavior = HumanBehavior()
