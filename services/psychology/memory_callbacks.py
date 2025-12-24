"""
Memory Callbacks Engine
-----------------------
Utilise activement la mémoire pour créer l'attachement.

Principe: "Elle se souvient de MOI" crée un sentiment d'importance.
Impact estimé: +3% conversion
"""

import random
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingEvent:
    """Un événement futur mentionné par l'utilisateur."""
    description: str
    expected_date: Optional[datetime]
    created_at: datetime
    checked: bool = False

    def to_dict(self) -> dict:
        """Convertit en dict pour stockage."""
        return {
            "description": self.description,
            "expected_date": self.expected_date.isoformat() if self.expected_date else None,
            "created_at": self.created_at.isoformat(),
            "checked": self.checked
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PendingEvent":
        """Crée depuis un dict avec gestion des erreurs de parsing."""
        # Safe datetime parsing
        try:
            expected_date = datetime.fromisoformat(data["expected_date"]) if data.get("expected_date") else None
        except (ValueError, TypeError):
            expected_date = None

        try:
            created_at = datetime.fromisoformat(data["created_at"])
        except (ValueError, TypeError):
            created_at = datetime.now()

        return cls(
            description=data["description"],
            expected_date=expected_date,
            created_at=created_at,
            checked=data.get("checked", False)
        )


class MemoryCallbacksEngine:
    """
    Moteur d'utilisation active de la mémoire.

    Fonctions:
    1. Identifier les événements à checker
    2. Générer des callbacks personnalisés
    3. Faire des références au passé partagé
    """

    # Templates de callbacks
    CALLBACK_TEMPLATES = {
        "event_checkin": [
            "dis, tu m'avais dit que {event}... ça s'est passé comment?",
            "c'était pas aujourd'hui ton {event}?",
            "alors, {event} c'est fini?",
            "dis, {event} ça a donné quoi?"
        ],
        "pet": [
            "comment va {pet}?",
            "et {pet}, il fait quoi là?",
            "{pet} va bien?"
        ],
        "hobby": [
            "t'as refait {hobby} récemment?",
            "ça se passe comment {hobby}?",
            "tu m'avais parlé de {hobby}... t'en es où?"
        ],
        "job": [
            "et le boulot, ça va?",
            "ton travail, c'est pas trop chaud en ce moment?",
            "t'avais des trucs au taf non?"
        ],
        "general": [
            "ça me rappelle ce que tu m'as dit sur {topic}...",
            "j'ai repensé à {topic} tout à l'heure",
            "tu sais, depuis que tu m'as parlé de {topic}, j'y pense"
        ],
        "emotion": [
            "tu vas mieux depuis {event}?",
            "j'espère que tu te sens mieux",
            "tu te sens comment aujourd'hui?"
        ]
    }

    # Patterns pour détecter des événements futurs
    EVENT_PATTERNS = [
        (r"demain j(?:e |'ai )(.+)", "demain"),
        (r"ce soir j(?:e |'ai )(.+)", "ce soir"),
        (r"cette semaine j(?:e |'ai )(.+)", "cette semaine"),
        (r"j'ai (?:un |une )?(\w+ \w*) (?:demain|ce soir|bientôt)", None),
        (r"je dois (.+) demain", "demain"),
        (r"j'ai rdv (.+)", None),
        (r"je passe (?:un |une )?(.+)", None),
    ]

    def should_do_callback(
        self,
        is_conversation_start: bool,
        hours_since_last: float,
        day_count: int
    ) -> bool:
        """
        Décide si on doit faire un callback mémoire.

        Args:
            is_conversation_start: Début de nouvelle conversation?
            hours_since_last: Heures depuis dernier message
            day_count: Jour de relation

        Returns:
            True si on doit faire un callback
        """
        if not is_conversation_start:
            return False

        if hours_since_last < 4:
            return False

        # Probabilité augmente avec le jour
        base_prob = {1: 0.25, 2: 0.40, 3: 0.55, 4: 0.65, 5: 0.70}
        prob = base_prob.get(min(day_count, 5), 0.55)

        # Augmente si longue absence
        if hours_since_last > 24:
            prob *= 1.3
        elif hours_since_last > 12:
            prob *= 1.15

        return random.random() < min(prob, 0.80)

    def generate_callback(
        self,
        memory: dict,
        pending_events: list[PendingEvent]
    ) -> Optional[str]:
        """
        Génère un message de callback basé sur la mémoire.

        Args:
            memory: Mémoire de l'utilisateur
            pending_events: Événements en attente

        Returns:
            Message de callback ou None
        """
        # 1. Check événements pending non checkés
        unchecked = [e for e in pending_events if not e.checked]
        if unchecked and random.random() < 0.7:
            event = random.choice(unchecked)
            template = random.choice(self.CALLBACK_TEMPLATES["event_checkin"])
            return template.format(event=event.description)

        # 2. Check mémoire pour détails personnels
        callbacks = []

        # Pet
        if memory.get("pet"):
            template = random.choice(self.CALLBACK_TEMPLATES["pet"])
            callbacks.append(template.format(pet=memory["pet"]))

        # Hobbies
        if memory.get("hobbies") and len(memory["hobbies"]) > 0:
            hobby = random.choice(memory["hobbies"])
            template = random.choice(self.CALLBACK_TEMPLATES["hobby"])
            callbacks.append(template.format(hobby=hobby))

        # Job
        if memory.get("travail"):
            template = random.choice(self.CALLBACK_TEMPLATES["job"])
            callbacks.append(template)

        # Facts généraux
        if memory.get("facts") and len(memory["facts"]) > 0:
            fact = random.choice(memory["facts"])
            template = random.choice(self.CALLBACK_TEMPLATES["general"])
            callbacks.append(template.format(topic=fact))

        # Problèmes/émotions
        if memory.get("problemes") and len(memory["problemes"]) > 0:
            template = random.choice(self.CALLBACK_TEMPLATES["emotion"])
            callbacks.append(template.format(event=memory["problemes"][0]))

        if callbacks:
            return random.choice(callbacks)

        return None

    def extract_pending_events(self, message: str) -> list[PendingEvent]:
        """
        Extrait les événements futurs mentionnés dans un message.

        Args:
            message: Message de l'utilisateur

        Returns:
            Liste d'événements extraits
        """
        events = []
        message_lower = message.lower()

        for pattern, time_hint in self.EVENT_PATTERNS:
            match = re.search(pattern, message_lower)
            if match:
                event_desc = match.group(1).strip()

                # Nettoyer
                event_desc = event_desc.rstrip('.')
                if len(event_desc) < 3 or len(event_desc) > 50:
                    continue

                event = PendingEvent(
                    description=event_desc,
                    expected_date=self._parse_time_hint(time_hint),
                    created_at=datetime.now()
                )
                events.append(event)
                logger.info(f"Extracted pending event: {event_desc}")

        return events

    def get_memory_instruction(self, memory: dict, force: bool = False) -> Optional[str]:
        """
        Génère une instruction pour utiliser la mémoire dans la réponse.

        Args:
            memory: Mémoire de l'utilisateur
            force: Si True, génère toujours une instruction (ignore probabilité)

        Returns:
            Instruction pour le LLM ou None
        """
        if not memory:
            return None

        # 50% chance de forcer utilisation mémoire (augmenté de 35%)
        # Ou 100% si force=True
        if not force and random.random() > 0.50:
            return None

        instructions = []

        # Prénom: priorité haute, utiliser souvent
        if memory.get("prenom"):
            instructions.append(f"UTILISE son prénom '{memory['prenom']}' dans ta réponse")

        if memory.get("travail"):
            instructions.append(f"Mentionne son travail ({memory['travail']}) naturellement")

        if memory.get("hobbies") and len(memory["hobbies"]) > 0:
            hobby = random.choice(memory["hobbies"])
            instructions.append(f"Fais référence à son hobby: {hobby}")

        if memory.get("problemes") and len(memory["problemes"]) > 0:
            prob = random.choice(memory["problemes"])
            instructions.append(f"Demande des nouvelles de: {prob}")

        if memory.get("ville"):
            instructions.append(f"Tu peux mentionner qu'il habite à {memory['ville']}")

        if memory.get("likes") and len(memory["likes"]) > 0:
            like = random.choice(memory["likes"])
            instructions.append(f"Fais référence à ce qu'il aime: {like}")

        if not instructions:
            return None

        # Prendre 1-2 instructions pour ne pas surcharger
        selected = random.sample(instructions, min(2, len(instructions)))
        return f"\n## RAPPEL MÉMOIRE (utilise naturellement)\n" + "\n".join(f"- {i}" for i in selected)

    def _parse_time_hint(self, hint: Optional[str]) -> Optional[datetime]:
        """Parse un indice temporel en datetime."""
        if not hint:
            return None

        now = datetime.now()

        if hint == "demain":
            return now + timedelta(days=1)
        elif hint == "ce soir":
            return now.replace(hour=20, minute=0)
        elif hint == "cette semaine":
            return now + timedelta(days=3)

        return None
