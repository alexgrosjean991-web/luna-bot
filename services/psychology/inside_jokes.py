"""
Inside Jokes Engine
-------------------
Crée et rappelle des moments partagés uniques pour renforcer l'attachement.

Principe: "On a NOTRE truc" crée un sentiment d'unicité et d'exclusivité.
Impact estimé: +5% conversion
"""

import random
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class JokeType(Enum):
    """Types d'inside jokes."""
    NICKNAME = "nickname"           # Surnom unique
    SHARED_MOMENT = "shared_moment" # Référence à un moment
    RUNNING_GAG = "running_gag"     # Blague récurrente
    QUIRK = "quirk"                 # Particularité du user


@dataclass
class InsideJoke:
    """Représente un inside joke."""
    joke_type: JokeType
    value: str
    context: str
    created_at: datetime = field(default_factory=datetime.now)
    times_referenced: int = 0
    last_referenced: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convertit en dict pour stockage JSON."""
        return {
            "joke_type": self.joke_type.value,
            "value": self.value,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "times_referenced": self.times_referenced,
            "last_referenced": self.last_referenced.isoformat() if self.last_referenced else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InsideJoke":
        """Crée depuis un dict."""
        return cls(
            joke_type=JokeType(data["joke_type"]),
            value=data["value"],
            context=data["context"],
            created_at=datetime.fromisoformat(data["created_at"]),
            times_referenced=data.get("times_referenced", 0),
            last_referenced=datetime.fromisoformat(data["last_referenced"]) if data.get("last_referenced") else None
        )


@dataclass
class JokeOpportunity:
    """Opportunité détectée pour créer un inside joke."""
    joke_type: JokeType
    content: str
    creation_message: str


class InsideJokesEngine:
    """
    Moteur de création et rappel d'inside jokes.

    Flow:
    1. Détecter opportunités dans messages user
    2. Créer le joke avec message approprié
    3. Stocker en mémoire
    4. Rappeler périodiquement
    """

    # Templates de callbacks
    CALLBACK_TEMPLATES = {
        JokeType.NICKNAME: [
            "coucou {value}",
            "coucou {value}",
            "{value}!!"
        ],
        JokeType.SHARED_MOMENT: [
            "ça me rappelle {value} mdrr",
            "comme la fois où {value}",
            "tu te souviens de {value}??"
        ],
        JokeType.RUNNING_GAG: [
            "{value}",
            "bon ok j'arrête avec {value}",
            "ça fait longtemps que j'ai pas dit {value}"
        ],
        JokeType.QUIRK: [
            "toi et ton {value}",
            "ah {value}... classique",
            "typique de toi ça {value}"
        ]
    }

    # Patterns pour détecter des opportunités de nickname
    NICKNAME_PATTERNS = [
        (r"\bchat\b|\bchats\b", ["mon petit chat", "chatounet"]),
        (r"\bchien\b|\btoutou\b", ["mon toutou", "petit chien"]),
        (r"j'ai renversé|j'ai cassé|je suis tombé", ["mon petit maladroit", "catastrophe ambulante"]),
        (r"j'adore (le |la |les )?(\w+)", ["mon gourmand de {match}"]),
        # FIXED: exclude "jouis" and other NSFW words
        (r"je joue (?!pt)(?:à |aux )?(\w+)", ["le gamer"]),
    ]

    def detect_opportunity(self, user_message: str, existing_jokes: list[InsideJoke]) -> Optional[JokeOpportunity]:
        """
        Détecte si le message contient une opportunité de créer un inside joke.

        Args:
            user_message: Message de l'utilisateur
            existing_jokes: Jokes existants pour éviter doublons

        Returns:
            JokeOpportunity si détectée, None sinon
        """
        message_lower = user_message.lower()
        existing_values = {j.value.lower() for j in existing_jokes}

        # Check pour nicknames
        opportunity = self._detect_nickname(message_lower, existing_values)
        if opportunity:
            return opportunity

        # Check pour moments drôles
        opportunity = self._detect_funny_moment(user_message, existing_values)
        if opportunity:
            return opportunity

        # Check pour quirks
        opportunity = self._detect_quirk(message_lower, existing_values)
        if opportunity:
            return opportunity

        return None

    def create_joke(self, opportunity: JokeOpportunity) -> InsideJoke:
        """Crée un inside joke à partir d'une opportunité."""
        return InsideJoke(
            joke_type=opportunity.joke_type,
            value=opportunity.content,
            context=opportunity.creation_message
        )

    def get_callback(self, joke: InsideJoke, day_count: int) -> Optional[str]:
        """
        Génère un message de callback pour un inside joke.

        Args:
            joke: Le joke à référencer
            day_count: Jour de la relation

        Returns:
            Message de callback ou None
        """
        # FIXED: Time-based cooldown - don't reference within 30 minutes
        if joke.last_referenced:
            minutes_since = (datetime.now() - joke.last_referenced).total_seconds() / 60
            if minutes_since < 30:
                logger.info(f"Inside joke '{joke.value}' skipped: referenced {minutes_since:.0f}min ago")
                return None

        # FIXED: Lower probability to avoid spam
        callback_probability = {1: 0.05, 2: 0.10, 3: 0.15, 4: 0.20, 5: 0.20}
        prob = callback_probability.get(min(day_count, 5), 0.15)

        # Reduce further if overused
        if joke.times_referenced > 5:
            prob *= 0.2
        elif joke.times_referenced > 3:
            prob *= 0.5

        if random.random() > prob:
            return None

        templates = self.CALLBACK_TEMPLATES[joke.joke_type]
        template = random.choice(templates)

        return template.format(value=joke.value)

    def should_create(self, day_count: int, existing_count: int) -> bool:
        """Décide si on peut créer un nouveau joke."""
        max_jokes = {1: 1, 2: 2, 3: 4, 4: 5, 5: 6}
        limit = max_jokes.get(min(day_count, 5), 4)
        return existing_count < limit

    def _detect_nickname(self, message: str, existing: set[str]) -> Optional[JokeOpportunity]:
        """Détecte opportunité de créer un surnom."""
        for pattern, nicknames in self.NICKNAME_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                nickname = random.choice(nicknames)

                # Remplacer {match} si présent
                if "{match}" in nickname and match.groups():
                    captured = match.group(len(match.groups()))
                    if captured:
                        nickname = nickname.format(match=captured)

                if nickname.lower() in existing:
                    continue

                return JokeOpportunity(
                    joke_type=JokeType.NICKNAME,
                    content=nickname,
                    creation_message=f"je peux t'appeler {nickname}?"
                )
        return None

    def _detect_funny_moment(self, message: str, existing: set[str]) -> Optional[JokeOpportunity]:
        """Détecte un moment drôle à référencer plus tard."""
        funny_patterns = [
            (r"j'ai renversé (.+)", "quand t'as renversé {0}"),
            (r"je suis tombé", "ta chute légendaire"),
            (r"j'ai oublié (.+)", "ta mémoire de poisson"),
            (r"je me suis trompé", "ton petit fail"),
            (r"j'ai fait une bêtise", "ta bêtise"),
        ]

        for pattern, moment_template in funny_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                if match.groups() and match.group(1):
                    moment = moment_template.format(match.group(1).strip())
                else:
                    moment = moment_template.replace(" {0}", "")

                if moment.lower() in existing:
                    continue

                return JokeOpportunity(
                    joke_type=JokeType.SHARED_MOMENT,
                    content=moment.strip(),
                    creation_message="mdrr je vais jamais oublier ça"
                )
        return None

    def _detect_quirk(self, message: str, existing: set[str]) -> Optional[JokeOpportunity]:
        """Détecte une particularité du user."""
        quirk_patterns = [
            (r"je suis toujours en retard", "tes retards légendaires"),
            (r"je dors (trop |pas assez)", "ton sommeil chaotique"),
            (r"j'oublie toujours", "ta mémoire de poisson"),
            (r"je mange (trop |que )", "tes habitudes alimentaires"),
            (r"je procrastine", "ta procrastination"),
        ]

        for pattern, quirk in quirk_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                if quirk.lower() in existing:
                    continue

                return JokeOpportunity(
                    joke_type=JokeType.QUIRK,
                    content=quirk,
                    creation_message=f"t'es vraiment comme ça toi mdrr"
                )
        return None
