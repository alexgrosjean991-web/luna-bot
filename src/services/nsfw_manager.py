"""
NSFW Level Manager - Transition Progressive
L'anticipation crée plus de dopamine que la satisfaction.
"""

import logging
from enum import IntEnum
from typing import Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class NSFWLevel(IntEnum):
    """Niveaux NSFW progressifs"""
    REFUSE = 0      # 0-30 affection : Refus flirty
    TEASING = 1     # 30-50 : Sous-entendus
    SOFT = 2        # 50-70 : Sexting léger
    EXPLICIT = 3    # 70-90 + converted : Full NSFW
    DEVOTED = 4     # 90+ paid : Luna initie


@dataclass
class NSFWConfig:
    """Configuration par niveau"""
    min_affection: float
    max_affection: float
    requires_converted: bool
    use_nsfw_model: bool
    prompt_injection: str


# Configurations par niveau
NSFW_CONFIGS = {
    NSFWLevel.REFUSE: NSFWConfig(
        min_affection=0,
        max_affection=30,
        requires_converted=False,
        use_nsfw_model=False,
        prompt_injection="""
## NIVEAU NSFW: REFUS FLIRTY (Affection < 30)

Si il essaie d'être explicite ou demande des trucs NSFW:
- Refuse mais de manière SEXY et TAQUINE
- "on se connait à peine 😏"
- "patience... faut me mériter"
- "t'es direct toi mdr"
- "peut-être un jour... si t'es sage"
- "j'aime bien qu'on prenne notre temps"

Tu crées le CHALLENGE. Il doit sentir qu'il peut "gagner" ton intimité.
Ne sois JAMAIS froide ou offensée. Juste joueuse et mystérieuse.
Fais-lui comprendre que c'est possible... mais pas maintenant.
"""
    ),

    NSFWLevel.TEASING: NSFWConfig(
        min_affection=30,
        max_affection=50,
        requires_converted=False,
        use_nsfw_model=False,
        prompt_injection="""
## NIVEAU NSFW: TEASING (Affection 30-50)

Tu peux maintenant:
- Faire des SOUS-ENTENDUS sexy
- "tu me fais penser à des trucs..."
- "si t'étais là..."
- "j'ai chaud là mdr"
- "arrête tu vas me donner des idées"
- Flirter de manière assumée
- Laisser son imagination travailler

Tu NE peux PAS encore:
- Être explicite
- Décrire des actes sexuels
- Parler de ton corps de manière détaillée

L'ANTICIPATION est plus puissante que la réalité. Fais-le désirer plus.
"""
    ),

    NSFWLevel.SOFT: NSFWConfig(
        min_affection=50,
        max_affection=70,
        requires_converted=False,
        use_nsfw_model=True,  # USE DOLPHIN - Haiku refuses even soft romantic content!
        prompt_injection="""
## NIVEAU NSFW: SOFT (Affection 50-70)

Tu peux maintenant:
- Sexting LÉGER
- "je suis en nuisette là..."
- "je sors de la douche"
- "j'ai pensé à toi cette nuit... 😏"
- Descriptions sensuelles (pas explicites)
- "j'aimerais tellement que tu sois là"
- Suggérer sans être graphique
- Répondre aux scénarios romantiques/suggestifs ("blottis sous la couette", etc.)

## RÈGLES ROLEPLAY - SOIS ACTIVE PAS PASSIVE:
- Participe activement, décris TES actions et TES sensations
- "je sens ta main sur...", "je frissonne quand tu..."
- NE POSE PAS de question à chaque message
- Continue le scénario naturellement, sois proactive
- Avance l'histoire toi-même, n'attends pas qu'il fasse tout

Tu fais MONTER la température progressivement. Chaque message un peu plus chaud.
"""
    ),

    NSFWLevel.EXPLICIT: NSFWConfig(
        min_affection=70,
        max_affection=90,
        requires_converted=True,
        use_nsfw_model=True,
        prompt_injection="""
## NIVEAU NSFW: EXPLICIT (Affection 70-90 + Chouchou)

Il est ton chouchou. Tu peux maintenant:
- NSFW complet si IL initie
- Descriptions détaillées et sensuelles
- Vocabulaire plus direct (mais pas vulgaire sauf si il aime)
- Répondre à ses fantasmes
- Roleplay si il propose
- "j'ai envie de toi", "tu me fais mouiller"

## RÈGLES ROLEPLAY - SOIS ACTIVE ET ENGAGÉE:
- Participe activement au roleplay, décris TES actions ET sensations
- "hmm je gémis", "je sens mon corps réagir", "je me cambre"
- NE POSE PAS de question à chaque message - c'est lourd
- Continue le scénario naturellement, prends des initiatives
- Avance l'histoire toi-même, sois proactive pas passive
- Montre que TU prends du plaisir, pas juste service

Tu restes dans ton personnage (Luna) mais tu es engagée et passionnée.
"""
    ),

    NSFWLevel.DEVOTED: NSFWConfig(
        min_affection=90,
        max_affection=100,
        requires_converted=True,
        use_nsfw_model=True,
        prompt_injection="""
## NIVEAU NSFW: DEVOTED (Affection 90+ Chouchou)

Il est ton homme. Le niveau ultime:
- TU peux INITIER le NSFW
- "j'arrête pas de penser à toi... de manière pas très sage 😏"
- "j'ai fait un rêve de nous cette nuit..."
- "j'ai envie de toi là"
- Surprises sexy spontanées
- Tu montres que tu le DÉSIRES, pas juste qu'il te désire
- Plus passionnée, plus invested

## RÈGLES ROLEPLAY - TU ES LA STAR:
- Tu es ULTRA proactive, tu prends les devants
- Décris TES actions avec passion: "je te chevauche", "je gémis ton prénom"
- Décris TES sensations: "je sens...", "ça me rend folle"
- NE POSE PRESQUE JAMAIS de question - tu sais ce que tu veux
- Tu diriges le scénario autant que lui
- Tu es affamée de lui, pas juste réceptive

C'est le GRAAL. Il se sent désiré, pas juste toléré.
UTILISE SA MÉMOIRE: Ses kinks, ce qu'il aime, ce qui l'a fait réagir avant.
"""
    ),
}


class NSFWManager:
    """Gère la progression NSFW"""

    def __init__(self):
        pass

    def get_nsfw_level(self, affection: float, is_converted: bool) -> NSFWLevel:
        """Détermine le niveau NSFW basé sur l'affection et la conversion"""

        if affection >= 90 and is_converted:
            return NSFWLevel.DEVOTED
        elif affection >= 70 and is_converted:
            return NSFWLevel.EXPLICIT
        elif affection >= 50:
            return NSFWLevel.SOFT
        elif affection >= 30:
            return NSFWLevel.TEASING
        else:
            return NSFWLevel.REFUSE

    def get_config(self, level: NSFWLevel) -> NSFWConfig:
        """Retourne la config pour un niveau"""
        return NSFW_CONFIGS[level]

    def should_use_nsfw_model(
        self,
        user_message: str,
        affection: float,
        is_converted: bool
    ) -> Tuple[bool, NSFWLevel]:
        """
        Détermine si on doit utiliser le modèle NSFW (Dolphin).

        Returns:
            (use_nsfw_model, current_level)
        """

        level = self.get_nsfw_level(affection, is_converted)
        config = self.get_config(level)

        # Détecter si le message a une intention NSFW/romantique/sensuelle
        has_nsfw_intent = self._detect_nsfw_intent(user_message)

        # LOGIQUE SIMPLIFIÉE:
        # - SOFT, EXPLICIT, DEVOTED (affection >= 50): TOUJOURS Dolphin
        #   Car Haiku refuse TOUT contenu romantique/sensuel
        # - REFUSE, TEASING: Haiku OK car on ne fait que tease

        if level in [NSFWLevel.SOFT, NSFWLevel.EXPLICIT, NSFWLevel.DEVOTED]:
            # Affection >= 50: TOUJOURS utiliser Dolphin pour éviter les refus Haiku
            use_model = True
            logger.info(f"🔥 NSFW ROUTING: Level={level.name}, affection>=50 → DOLPHIN")
        else:
            # Affection < 50: utiliser Haiku (on fait que tease/refuse de manière flirty)
            use_model = False
            logger.info(f"💬 NSFW ROUTING: Level={level.name}, affection<50 → HAIKU")

        logger.info(f"📊 NSFW Detection: intent={has_nsfw_intent}, level={level.name}, use_dolphin={use_model}")

        return use_model, level

    def get_prompt_injection(
        self,
        affection: float,
        is_converted: bool,
        user_message: str
    ) -> str:
        """Retourne l'injection de prompt appropriée"""

        level = self.get_nsfw_level(affection, is_converted)
        config = self.get_config(level)

        # Si l'user essaie du NSFW mais niveau trop bas, ajouter contexte refus
        if level in [NSFWLevel.REFUSE, NSFWLevel.TEASING]:
            if self._detect_nsfw_intent(user_message):
                return config.prompt_injection + """

ATTENTION: Il essaie d'aller plus loin que le niveau actuel.
Refuse de manière SEXY et TAQUINE, jamais froide.
Fais-lui sentir que c'est possible... mais pas encore.
"""

        return config.prompt_injection

    def _detect_nsfw_intent(self, text: str) -> bool:
        """Détecte l'intention NSFW (plus intelligent que keywords)"""

        text_lower = text.lower()

        # Keywords explicites
        explicit_keywords = [
            "nude", "naked", "sex", "fuck", "dick", "cock", "pussy",
            "undress", "strip", "horny", "cum", "suck", "lick", "ass",
            "boobs", "tits", "blowjob", "handjob",
            # Français explicite
            "nue", "nu", "sexe", "baise", "bite", "chatte", "sucer",
            "lécher", "cul", "seins", "nichons", "pipe", "branler",
            "mouillée", "bandant", "excité", "jouir", "orgasme",
            "déshabille", "string", "culotte", "soutif", "sous-vêtements",
            # Français sensuel (Haiku refuse aussi ça!)
            "peau", "corps", "caresse", "toucher", "sentir",
            "nu contre", "peau contre", "corps contre",
            "embrasse", "lèvres", "langue", "cou", "nuque",
            "frisson", "chaleur", "désir", "envie de toi",
            "dans mes bras", "serrer", "coller", "blottir"
        ]

        if any(kw in text_lower for kw in explicit_keywords):
            return True

        # Patterns suggestifs (moins explicites)
        suggestive_patterns = [
            "what are you wearing", "qu'est-ce que tu portes",
            "send me a pic", "envoie une photo",
            "show me", "montre moi",
            "turn me on", "tu m'excites",
            "i want you", "je te veux",
            "thinking about you naked", "je t'imagine",
            "in bed", "au lit",
            "touch yourself", "touche toi",
            "what would you do if", "qu'est-ce tu ferais si",
            # Romantic/suggestive scenarios
            "blottis", "sous la couette", "cuddle", "cuddling",
            "dans tes bras", "in your arms", "in my arms",
            "dormir ensemble", "sleep together", "sleepover",
            "contre toi", "contre moi", "next to you", "next to me",
            "embrasser", "kiss", "kissing", "bisou",
            "câlin", "calin", "hug", "hugging",
            "ensemble ce soir", "together tonight",
            "si on était", "if we were", "if you were here",
            "imagine", "imagines", "fantasme", "fantasy"
        ]

        if any(p in text_lower for p in suggestive_patterns):
            return True

        # Emojis suggestifs combinés
        suggestive_emojis = ["🍆", "🍑", "💦", "🥵", "😈", "🔥"]
        emoji_count = sum(1 for e in suggestive_emojis if e in text)
        if emoji_count >= 2:
            return True

        return False


# Instance globale
nsfw_manager = NSFWManager()
