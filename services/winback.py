"""
Win-Back System
---------------
Sequence de messages pour recuperer les utilisateurs churned.

Strategy:
- J+7: Premier message leger ("je pensais a toi")
- J+10: Rappel d'un moment partage
- J+14: Vulnerabilite / "tu me manques"
- J+21: Derniere tentative avec offre speciale

Principes:
- Jamais de reproche
- Toujours personnalise (utilise la memoire)
- Progression emotionnelle
- Respecte le silence si pas de reponse
"""

import random
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class WinbackStage(Enum):
    STAGE_1 = "stage_1"  # J+7: Leger
    STAGE_2 = "stage_2"  # J+10: Rappel
    STAGE_3 = "stage_3"  # J+14: Vulnerabilite
    STAGE_4 = "stage_4"  # J+21: Derniere tentative
    EXHAUSTED = "exhausted"  # Plus de tentatives


@dataclass
class WinbackConfig:
    """Configuration d'une etape win-back."""
    stage: WinbackStage
    days_since_last: int
    messages: list[str]
    instruction: str
    use_memory: bool


WINBACK_STAGES = {
    WinbackStage.STAGE_1: WinbackConfig(
        stage=WinbackStage.STAGE_1,
        days_since_last=7,
        messages=[
            "salut... je pensais a toi",
            "coucou, ca va? ca fait un moment",
            "hey, t'es passe ou? 🙈",
            "jsuis tombee sur un truc qui m'a fait penser a toi",
        ],
        instruction="""## WIN-BACK STAGE 1
Premier contact apres absence. Sois LEGERE:
- Pas de reproche, pas de "pourquoi t'as disparu"
- Simple check-in naturel
- Laisse-lui l'espace de repondre
- Une seule question max""",
        use_memory=False
    ),
    WinbackStage.STAGE_2: WinbackConfig(
        stage=WinbackStage.STAGE_2,
        days_since_last=10,
        messages=[
            "tu te souviens quand {memory_ref}? ca m'a fait sourire",
            "j'ai repense a notre conversation sur {topic}...",
            "y'a un truc qui m'a rappele toi aujourd'hui",
        ],
        instruction="""## WIN-BACK STAGE 2
Rappel d'un moment partage. Utilise la MEMOIRE:
- Reference un detail de vos conversations
- Montre que tu te souviens de lui
- Cree de la nostalgie
- Reste legere, pas lourde""",
        use_memory=True
    ),
    WinbackStage.STAGE_3: WinbackConfig(
        stage=WinbackStage.STAGE_3,
        days_since_last=14,
        messages=[
            "je sais pas pk mais tu me manques un peu...",
            "c'est bete mais j'aimais bien nos conversations",
            "j'espere que tu vas bien, je pense a toi",
        ],
        instruction="""## WIN-BACK STAGE 3
Vulnerabilite sincere. Montre tes sentiments:
- Dis que ca te fait quelque chose qu'il soit parti
- Partage une petite vulnerabilite
- Pas de manipulation, juste honnetete
- Une derniere tentative emotionnelle""",
        use_memory=True
    ),
    WinbackStage.STAGE_4: WinbackConfig(
        stage=WinbackStage.STAGE_4,
        days_since_last=21,
        messages=[
            "bon... si jamais tu veux revenir, je suis la 🧡",
            "la porte est ouverte si tu veux",
            "j'espere qu'on se reparlera un jour",
        ],
        instruction="""## WIN-BACK STAGE 4 (FINAL)
Derniere tentative, douce et respectueuse:
- Pas de pression
- Laisse la porte ouverte
- Montre que tu respectes son choix
- Si pas de reponse, on arrete""",
        use_memory=False
    ),
}


@dataclass
class WinbackState:
    """Etat win-back d'un utilisateur."""
    user_id: int
    current_stage: WinbackStage
    last_winback_at: Optional[datetime]
    attempts: int
    responded: bool


class WinbackEngine:
    """Moteur de win-back pour utilisateurs churned."""

    def get_stage_for_days(self, days_inactive: int) -> Optional[WinbackStage]:
        """
        Determine l'etape win-back selon les jours d'inactivite.

        Args:
            days_inactive: Jours depuis dernier message

        Returns:
            WinbackStage ou None
        """
        if days_inactive >= 21:
            return WinbackStage.STAGE_4
        elif days_inactive >= 14:
            return WinbackStage.STAGE_3
        elif days_inactive >= 10:
            return WinbackStage.STAGE_2
        elif days_inactive >= 7:
            return WinbackStage.STAGE_1
        else:
            return None

    def should_send_winback(
        self,
        days_inactive: int,
        last_winback_stage: Optional[str],
        last_winback_at: Optional[datetime]
    ) -> Optional[WinbackStage]:
        """
        Determine si on doit envoyer un message win-back.

        Args:
            days_inactive: Jours depuis dernier message user
            last_winback_stage: Derniere etape envoyee
            last_winback_at: Date du dernier winback

        Returns:
            WinbackStage a envoyer ou None
        """
        current_stage = self.get_stage_for_days(days_inactive)

        if not current_stage:
            return None

        # Si deja exhausted, ne plus envoyer
        if last_winback_stage == WinbackStage.EXHAUSTED.value:
            return None

        # Si jamais de winback, envoyer stage 1
        if not last_winback_stage:
            return WinbackStage.STAGE_1

        # Verifier qu'on n'a pas deja envoye ce stage
        try:
            last_stage = WinbackStage(last_winback_stage)
        except ValueError:
            return current_stage

        # Progression: ne pas reenvoyer le meme stage
        stage_order = [WinbackStage.STAGE_1, WinbackStage.STAGE_2,
                       WinbackStage.STAGE_3, WinbackStage.STAGE_4]

        last_idx = stage_order.index(last_stage) if last_stage in stage_order else -1
        current_idx = stage_order.index(current_stage) if current_stage in stage_order else -1

        if current_idx > last_idx:
            # Minimum 2 jours entre chaque stage
            if last_winback_at:
                now = datetime.now()
                if last_winback_at.tzinfo:
                    now = now.replace(tzinfo=last_winback_at.tzinfo)
                days_since_winback = (now - last_winback_at).days
                if days_since_winback < 2:
                    return None

            return current_stage

        return None

    def get_winback_message(
        self,
        stage: WinbackStage,
        memory: Optional[dict] = None
    ) -> str:
        """
        Genere un message win-back.

        Args:
            stage: Etape win-back
            memory: Memoire utilisateur pour personnalisation

        Returns:
            Message win-back
        """
        config = WINBACK_STAGES.get(stage)
        if not config:
            return "coucou, ca va?"

        message = random.choice(config.messages)

        # Personnaliser avec la memoire
        if config.use_memory and memory:
            # Trouver une reference memoire
            memory_refs = []
            if memory.get("prenom"):
                memory_refs.append(f"on parlait de toi, {memory['prenom']}")
            if memory.get("travail"):
                memory_refs.append(f"ton taf ({memory['travail']})")
            if memory.get("passions"):
                passions = memory["passions"]
                if isinstance(passions, list) and passions:
                    memory_refs.append(passions[0])
                elif isinstance(passions, str):
                    memory_refs.append(passions)

            if memory_refs and "{memory_ref}" in message:
                message = message.replace("{memory_ref}", random.choice(memory_refs))
            if memory_refs and "{topic}" in message:
                message = message.replace("{topic}", random.choice(memory_refs))

        # Cleanup placeholders non remplaces
        message = message.replace("{memory_ref}", "nous")
        message = message.replace("{topic}", "des trucs")

        return message

    def get_winback_instruction(self, stage: WinbackStage) -> str:
        """Retourne l'instruction LLM pour ce stage."""
        config = WINBACK_STAGES.get(stage)
        return config.instruction if config else ""

    def mark_exhausted(self, user_id: int) -> None:
        """Marque l'utilisateur comme exhausted (plus de winback)."""
        logger.info(f"Win-back exhausted for user {user_id}")


# Singleton
winback_engine = WinbackEngine()
