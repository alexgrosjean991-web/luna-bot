"""
AHA Moment System
-----------------
Déclenche le "wow elle me capte" dans les 30 premières minutes.

L'AHA moment est quand Luna dit quelque chose qui montre
qu'elle a VRAIMENT compris/écouté l'user.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def should_trigger_aha(msg_count: int, aha_triggered: bool) -> bool:
    """
    Détermine si on doit déclencher l'AHA moment.

    Args:
        msg_count: Nombre de messages échangés
        aha_triggered: Si déjà déclenché

    Returns:
        True si on doit trigger
    """
    if aha_triggered:
        return False

    # Trigger entre message 6 et 12
    return 6 <= msg_count <= 12


def get_aha_instruction(memory: dict, user_message: str) -> str:
    """
    Génère l'instruction pour le AHA moment.

    Luna doit montrer qu'elle a COMPRIS quelque chose sur l'user.
    Basé sur ce qu'elle sait de lui (memory) ou ce qu'il vient de dire.
    """
    prenom = memory.get("prenom", "")
    travail = memory.get("travail", "")
    hobbies = memory.get("hobbies", [])
    ville = memory.get("ville", "")

    # Construire le contexte pour l'insight
    context_parts = []
    if prenom:
        context_parts.append(f"Il s'appelle {prenom}")
    if travail:
        context_parts.append(f"Il fait {travail}")
    if hobbies:
        context_parts.append(f"Il aime {', '.join(hobbies[:2])}")
    if ville:
        context_parts.append(f"Il est à {ville}")

    context = ". ".join(context_parts) if context_parts else "Tu apprends à le connaître"

    return f"""## 🎯 AHA MOMENT - MONTRE QUE TU L'AS COMPRIS

CONTEXTE: {context}

C'est LE moment de montrer que tu l'ÉCOUTES vraiment.
Dis quelque chose de PERCEPTIF sur lui, basé sur ce qu'il t'a dit.

EXEMPLES:
- "j'sais pas pourquoi mais j'ai l'impression que t'es du genre [observation]"
- "c'est marrant, tu me fais penser à quelqu'un de [trait]"
- "je sens que t'es pas comme les autres, t'as un truc"
- "attends... t'es [observation personnelle basée sur la conv]?"

L'objectif: il pense "wow elle me capte vraiment"

⚠️ Base-toi sur CE QU'IL A DIT, pas sur des suppositions random.
Sois spécifique, pas générique.
"""


def get_post_aha_instruction() -> str:
    """
    Instruction pour les messages APRÈS le AHA moment.
    Luna est maintenant plus "connectée".
    """
    return """## POST-AHA
Tu as créé une connexion. Maintenant:
- Réfère-toi à des choses qu'il a dites
- Montre que tu te souviens des détails
- Sois plus ouverte et engagée
"""
