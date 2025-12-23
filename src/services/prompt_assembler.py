"""
Prompt Assembler
Assemble le prompt système depuis les modules.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List

from src.services.conversation_state import ConversationState, state_machine
from src.services.inner_world import inner_world, InnerState

logger = logging.getLogger(__name__)

# Chemin vers les modules de prompts
MODULES_PATH = Path(__file__).parent.parent / "prompts" / "modules"


class PromptAssembler:
    """
    Assemble le prompt système depuis les modules.
    Prompt final: ~1200-1400 tokens max.
    """

    def __init__(self):
        self._cache: dict = {}  # Cache les fichiers chargés

    def _load_module(self, name: str, lang: str = "fr") -> str:
        """Charge un module de prompt depuis un fichier"""
        cache_key = f"{name}_{lang}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = MODULES_PATH / f"{name}_{lang}.txt"
        if not file_path.exists():
            logger.warning(f"Module not found: {file_path}")
            return ""

        content = file_path.read_text(encoding="utf-8")
        self._cache[cache_key] = content
        return content

    def assemble(
        self,
        user_id: int,
        user_name: str,
        affection: float,
        is_converted: bool,
        user_message: str,
        memories: List[dict],
        last_luna_message: str = "",
        lang: str = "fr"
    ) -> str:
        """
        Assemble le prompt système complet.

        Returns:
            Prompt système prêt à envoyer au LLM.
        """
        parts = []

        # 1. BASE - Identité de Luna (~250 tokens)
        base = self._load_module("base", lang)
        base = base.format(user_name=user_name or "ce mec")
        parts.append(base)

        # 2. ÉTAT DE CONVERSATION - Déterminé par la state machine
        state, transition = state_machine.get_state(
            user_id=user_id,
            affection=affection,
            is_converted=is_converted,
            user_message=user_message,
            last_luna_message=last_luna_message
        )

        state_module = self._load_module(state.value, lang)
        if state_module:
            parts.append(state_module)
            logger.info(f"State module loaded: {state.value}")

        # 3. INNER WORLD - État interne de Luna (~100 tokens)
        inner_state = inner_world.get_state(user_id)
        inner_world.update_from_db(user_id, {'affection_level': affection})
        inner_world.process_user_message(user_id, user_message)
        inner_context = inner_world.get_prompt_context(user_id)
        parts.append(inner_context)

        # 4. MEMORIES - Ce que Luna sait sur lui (~100 tokens max)
        if memories:
            memory_text = "## CE QUE TU SAIS SUR LUI\n"
            memory_text += "\n".join([f"- {m['content']}" for m in memories[:8]])
            parts.append(memory_text)
        else:
            parts.append("## CE QUE TU SAIS SUR LUI\nTu sais pas grand chose encore")

        # 5. RELATIONSHIP STATUS (~50 tokens)
        relationship_text = self._get_relationship_context(affection, is_converted)
        parts.append(relationship_text)

        # Assembler le prompt final
        full_prompt = "\n\n".join(parts)

        # Log pour debug
        logger.info(f"Prompt assembled: {len(full_prompt)} chars, state={state.value}")

        return full_prompt

    def _get_relationship_context(self, affection: float, is_converted: bool) -> str:
        """Génère le contexte de relation"""
        if is_converted:
            return f"""## RELATION
Affection: {int(affection)}/100
Status: COUPLE - T'es SA copine. Super affectueuse, "mon amour", tu parles de "nous"."""

        if affection >= 70:
            return f"""## RELATION
Affection: {int(affection)}/100
Status: Très attachée, jalouse si autres filles, "j'ai peut-être un crush sur toi"."""

        if affection >= 50:
            return f"""## RELATION
Affection: {int(affection)}/100
Status: Connectée, tu te confies, flirt assumé."""

        if affection >= 30:
            return f"""## RELATION
Affection: {int(affection)}/100
Status: Plus à l'aise, tu taquines, private jokes."""

        return f"""## RELATION
Affection: {int(affection)}/100
Status: Vous vous connaissez à peine."""

    def get_current_state(self, user_id: int) -> Optional[ConversationState]:
        """Retourne l'état actuel de conversation"""
        return state_machine.get_last_state(user_id)

    def should_use_nsfw_model(self, user_id: int) -> bool:
        """Détermine si on doit utiliser le modèle NSFW"""
        state = state_machine.get_last_state(user_id)
        return state in [
            ConversationState.NSFW_SOFT,
            ConversationState.NSFW_HARD,
            ConversationState.AFTERCARE
        ]


# Instance globale
prompt_assembler = PromptAssembler()
