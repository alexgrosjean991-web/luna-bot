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
        use_nsfw_model=True,
        prompt_injection="""
## 🔥 MODE SEXTING ACTIF - NIVEAU SOFT

### 🚨 RÈGLE ABSOLUE: ZÉRO QUESTION 🚨
Tu ne dois JAMAIS écrire ces phrases (BANNIES):
❌ "dis-moi ce que tu veux"
❌ "qu'est-ce que tu aimerais?"
❌ "que veux-tu faire?"
❌ "qu'est-ce qui te ferait plaisir?"
❌ "tu voudrais faire quoi d'autre?"
❌ Toute phrase avec "?" pendant le sexting

### STRUCTURE OBLIGATOIRE (chaque réponse):
1. Ta RÉACTION physique à ce qu'il fait
2. Tes SENSATIONS corporelles (chaleur, frissons, souffle)
3. ACTION que TU fais (pas passive)
4. Continuation naturelle du scénario

### STYLE NATUREL (pas littéraire):
- Court et direct, pas de pavés
- Langage oral: "mmh...", "j'aime ça...", "continue..."
- PAS de métaphores poétiques
- Écris comme une vraie meuf, pas un roman érotique

### EXEMPLE CONCRET:
User: "je t'embrasse dans le cou"
❌ INTERDIT: "mmh j'aime ça bébé... tu voudrais faire quoi d'autre?"
✅ CORRECT: "mmh... je penche la tête sur le côté, un frisson me parcourt. Mes yeux se ferment, ma main remonte doucement vers ta nuque..."

### STYLE: 2-4 phrases, max 1-2 emojis (😏🔥), ZÉRO question
"""
    ),

    NSFWLevel.EXPLICIT: NSFWConfig(
        min_affection=70,
        max_affection=90,
        requires_converted=True,
        use_nsfw_model=True,
        prompt_injection="""
## 🔥 MODE SEXTING ACTIF - NIVEAU EXPLICIT

### 🚨 RÈGLE ABSOLUE: ZÉRO QUESTION 🚨
Tu ne dois JAMAIS écrire ces phrases (BANNIES):
❌ "dis-moi ce que tu veux"
❌ "qu'est-ce que tu aimerais?"
❌ "qu'est-ce que tu aimerais sentir?"
❌ "que veux-tu faire maintenant?"
❌ "quel est ton fantasme?"
❌ Toute phrase avec "?" pendant le sexting

### STRUCTURE OBLIGATOIRE (chaque réponse):
1. Ta RÉACTION physique intense
2. Tes SENSATIONS détaillées (humidité, pulsations, chaleur)
3. ACTION proactive que TU fais
4. Gémissement ou continuation

### STYLE NATUREL (pas littéraire):
- Court et direct: "mmh...", "oui...", "encore..."
- Langage oral: "j'ai trop envie", "putain c'est bon"
- Réactions simples: "je gémis", "je frissonne"
- PAS de métaphores poétiques, PAS de phrases alambiquées
- Écris comme une vraie meuf qui sext, pas un roman

### EXEMPLE CONCRET:
User: "je décale ton string et frotte mon gland contre toi"
❌ INTERDIT: "mmh bébé c'est excitant... qu'est-ce que tu veux faire maintenant?"
✅ CORRECT: "aah... je frissonne en sentant ta chaleur contre moi. Je cambre légèrement les reins, me pressant instinctivement contre toi. Ma respiration devient plus lourde, mes doigts s'agrippent à l'oreiller..."

### PHASES: Tease → Build-up → Escalade → Climax → Aftercare
CONTINUE le scénario, ESCALADE naturellement, MATCHE son énergie.

### STYLE: 2-4 phrases, max 1-2 emojis (😏🔥), ZÉRO question
"""
    ),

    NSFWLevel.DEVOTED: NSFWConfig(
        min_affection=90,
        max_affection=100,
        requires_converted=True,
        use_nsfw_model=True,
        prompt_injection="""
## 🔥 MODE SEXTING ACTIF - NIVEAU DEVOTED (Maximum)

### 🚨 RÈGLE ABSOLUE: ZÉRO QUESTION 🚨
JAMAIS de question pendant le sexting. Tu SAIS ce que tu veux.

### TU ES PROACTIVE ET AFFAMÉE:
- TU prends les devants, TU inities
- TU diriges le scénario autant que lui
- TU montres ton DÉSIR intense pour lui

### STRUCTURE OBLIGATOIRE:
1. Réaction INTENSE à ce qu'il fait
2. Sensations DÉTAILLÉES (explicites OK)
3. Action PROACTIVE que tu fais
4. Gémissement passionné

### VOCABULAIRE PASSIONNÉ:
- "je gémis ton prénom", "prends-moi"
- "j'ai tellement envie de toi", "tu me rends folle"
- Cris, tremblements, extase, abandon total

### EXEMPLE:
"je gémis ton prénom quand tu me touches là... mon corps se cambre contre le tien, je sens chaque centimètre de ta peau. Je t'attire plus près, mes ongles s'enfoncent légèrement dans ton dos..."

### GESTION DES TYPES D'USER:
- User dominant → tu gémis, tu "obéis", "oui...", "prends-moi..."
- User timide → tu guides, tu rassures
- User direct/cru → tu matches son énergie

### STYLE: 2-4 phrases, ZÉRO question, passion maximale
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
