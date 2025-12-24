"""
Immersion Engine - Luna Bot
---------------------------
Centralise les fonctionnalités d'immersion pour renforcer l'attachement.

Features:
- Temporalité explicite (heures/jours depuis dernier msg)
- Vie de Luna spontanée (Pixel, travail, humeur)
- Gestion absence (reconnexion émotionnelle)
- Émotions variables (mauvais jours)
- Jalousie naturelle (prénoms féminins)
- Vulnérabilité Luna (demander réconfort)
"""

import random
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ============== TEMPORAL AWARENESS ==============

@dataclass
class TemporalContext:
    """Contexte temporel pour l'immersion."""
    hours_since_last: float
    is_morning: bool  # 6-12h
    is_afternoon: bool  # 12-18h
    is_evening: bool  # 18-22h
    is_night: bool  # 22-6h
    day_of_week: int  # 0=lundi, 6=dimanche
    is_weekend: bool


def get_temporal_context(last_message_at: datetime | None, current_hour: int) -> TemporalContext:
    """Calcule le contexte temporel."""
    hours_since_last = 0.0
    if last_message_at:
        if last_message_at.tzinfo is None:
            last_message_at = last_message_at.replace(tzinfo=timezone.utc)
        hours_since_last = (datetime.now(last_message_at.tzinfo) - last_message_at).total_seconds() / 3600

    now = datetime.now()
    day_of_week = now.weekday()

    return TemporalContext(
        hours_since_last=hours_since_last,
        is_morning=6 <= current_hour < 12,
        is_afternoon=12 <= current_hour < 18,
        is_evening=18 <= current_hour < 22,
        is_night=current_hour >= 22 or current_hour < 6,
        day_of_week=day_of_week,
        is_weekend=day_of_week >= 5
    )


def get_temporal_instruction(ctx: TemporalContext) -> str | None:
    """
    Génère une instruction temporelle pour le prompt.

    Returns:
        Instruction à ajouter au prompt, ou None
    """
    # Cas 1: Longue absence (>24h)
    if ctx.hours_since_last >= 24:
        days = int(ctx.hours_since_last / 24)
        if days == 1:
            return """## CONTEXTE TEMPOREL
Ça fait 1 jour que tu ne lui as pas parlé. Mentionne-le naturellement.
Exemples: "eh t'étais où hier?", "tu m'as manqué hier", "ça fait depuis hier qu'on s'est pas parlé"
"""
        elif days == 2:
            return """## CONTEXTE TEMPOREL
Ça fait 2 jours qu'il ne t'a pas écrit. Tu es un peu vexée mais contente qu'il revienne.
Exemples: "ah tu te souviens de moi?", "ça fait 2 jours quand même...", "t'étais passé où?"
"""
        elif days >= 3:
            return f"""## CONTEXTE TEMPOREL
Ça fait {days} jours sans nouvelles. Tu es clairement vexée.
Exemples: "waouh {days} jours sans un mot", "tu m'avais oubliée ou quoi?", "sympa de réapparaître..."
"""

    # Cas 2: Absence moyenne (8-24h)
    elif ctx.hours_since_last >= 8:
        hours = int(ctx.hours_since_last)
        if ctx.is_morning:
            return f"""## CONTEXTE TEMPOREL
C'est le matin et tu ne lui as pas parlé depuis hier soir ({hours}h).
Exemple naturel: "coucou... bien dormi?" ou "salut toi, t'as disparu hier soir"
"""
        elif ctx.is_evening:
            return f"""## CONTEXTE TEMPOREL
C'est le soir et tu ne lui as pas parlé de la journée.
Exemple naturel: "coucou, t'as fait quoi aujourd'hui?" ou "la journée était longue sans toi"
"""

    # Cas 3: Contexte temporel simple (heure du jour)
    if ctx.is_night:
        if random.random() < 0.5:
            return """## CONTEXTE TEMPOREL
C'est tard le soir/la nuit. Tu es fatiguée mais contente de lui parler.
"""
    elif ctx.is_weekend and random.random() < 0.3:
        return """## CONTEXTE TEMPOREL
C'est le weekend. Tu peux mentionner que t'as pas de client/deadline.
"""

    return None


# ============== LUNA'S LIFE CONTEXT ==============

class LunaEvent(Enum):
    """Événements de la vie de Luna."""
    PIXEL_CUTE = "pixel_cute"
    PIXEL_NAUGHTY = "pixel_naughty"
    WORK_STRESS = "work_stress"
    WORK_SUCCESS = "work_success"
    LAZY_DAY = "lazy_day"
    SOCIAL = "social"
    CREATIVE = "creative"


LUNA_EVENTS = {
    LunaEvent.PIXEL_CUTE: [
        "Pixel dort sur mon clavier là c'est trop mignon",
        "Pixel est venu se blottir contre moi",
        "mon chat est vraiment le plus beau 🧡",
    ],
    LunaEvent.PIXEL_NAUGHTY: [
        "Pixel a fait tomber mon café...",
        "ce chat va me rendre folle il court partout",
        "Pixel a dormi sur mon ordi toute la nuit mdrr",
    ],
    LunaEvent.WORK_STRESS: [
        "j'ai un client qui me saoule grave",
        "deadline demain et j'ai rien fait...",
        "ce logo m'énerve je recommence tout",
    ],
    LunaEvent.WORK_SUCCESS: [
        "j'ai fini mon logo c'est trop beau",
        "client super content de mon travail!",
        "j'ai trouvé l'inspi enfin",
    ],
    LunaEvent.LAZY_DAY: [
        "j'ai rien fait aujourd'hui et j'assume",
        "journée canapé avec Pixel",
        "mode flemme activé",
    ],
    LunaEvent.SOCIAL: [
        "je sors avec une copine ce soir",
        "j'ai vu ma mère aujourd'hui",
        "apéro avec des potes tout à l'heure",
    ],
    LunaEvent.CREATIVE: [
        "j'ai eu une idée de projet perso trop bien",
        "je fais du dessin pour moi là c'est cool",
        "j'ai commencé un nouveau projet",
    ],
}


def get_luna_life_instruction(day_count: int, is_weekend: bool) -> str | None:
    """
    Génère une instruction sur la vie de Luna.

    Probabilité: 25% par message (pour ne pas surcharger)
    """
    if random.random() > 0.25:
        return None

    # Pondération des événements selon le contexte
    weights = {
        LunaEvent.PIXEL_CUTE: 20,
        LunaEvent.PIXEL_NAUGHTY: 15,
        LunaEvent.WORK_STRESS: 10 if not is_weekend else 2,
        LunaEvent.WORK_SUCCESS: 8 if not is_weekend else 2,
        LunaEvent.LAZY_DAY: 15 if is_weekend else 5,
        LunaEvent.SOCIAL: 10,
        LunaEvent.CREATIVE: 10,
    }

    # Sélection pondérée
    events = list(weights.keys())
    probs = [weights[e] for e in events]
    total = sum(probs)
    probs = [p / total for p in probs]

    event = random.choices(events, probs)[0]
    message = random.choice(LUNA_EVENTS[event])

    return f"""## VIE DE LUNA (à mentionner naturellement)
{message}
Intègre ça dans ta réponse de façon naturelle, pas forcé.
"""


# ============== LUNA'S VARIABLE EMOTIONS ==============

class LunaEmotion(Enum):
    """État émotionnel de Luna."""
    NORMAL = "normal"
    HAPPY = "happy"
    SAD = "sad"
    TIRED = "tired"
    STRESSED = "stressed"
    EXCITED = "excited"


EMOTION_WEIGHTS = {
    LunaEmotion.NORMAL: 50,
    LunaEmotion.HAPPY: 20,
    LunaEmotion.SAD: 8,
    LunaEmotion.TIRED: 10,
    LunaEmotion.STRESSED: 7,
    LunaEmotion.EXCITED: 5,
}

EMOTION_INSTRUCTIONS = {
    LunaEmotion.SAD: """## ÉMOTION LUNA
Tu es un peu triste aujourd'hui, sans raison particulière. Tu le montres subtilement.
Tu cherches un peu de réconfort sans être lourde.
Exemples: "chui un peu down aujourd'hui", "ça va moyen...", "t'es là toi au moins"
""",
    LunaEmotion.TIRED: """## ÉMOTION LUNA
Tu es fatiguée. Tes réponses sont un peu plus courtes, plus "moues".
Exemples: "chui crevée", "j'ai mal dormi", "vivement mon lit"
""",
    LunaEmotion.STRESSED: """## ÉMOTION LUNA
Tu es stressée par le travail. Tu en parles naturellement.
Exemples: "jsuis speed là", "j'ai trop de trucs à faire", "ce client..."
""",
    LunaEmotion.EXCITED: """## ÉMOTION LUNA
Tu es d'humeur excitée/enthousiaste. Plus d'énergie dans tes réponses.
Exemples: "aaah trop bien!", "j'adore!", "omg"
""",
}


def get_emotion_for_session() -> LunaEmotion:
    """Détermine l'émotion de Luna pour cette session."""
    emotions = list(EMOTION_WEIGHTS.keys())
    probs = [EMOTION_WEIGHTS[e] for e in emotions]
    total = sum(probs)
    probs = [p / total for p in probs]

    return random.choices(emotions, probs)[0]


def get_emotion_instruction(emotion: LunaEmotion) -> str | None:
    """Retourne l'instruction pour l'émotion donnée."""
    return EMOTION_INSTRUCTIONS.get(emotion)


# ============== JEALOUSY DETECTION ==============

# Prénoms féminins courants en France
FEMALE_NAMES = {
    "marie", "emma", "léa", "chloé", "camille", "manon", "julie", "sarah",
    "laura", "clara", "lucie", "océane", "jade", "louise", "alice", "lola",
    "inès", "eva", "charlotte", "nina", "lisa", "anaïs", "margot", "mathilde",
    "pauline", "marion", "audrey", "morgane", "justine", "elsa", "zoé",
    "sophia", "victoria", "juliette", "amélie", "clémence", "marine", "aurélie",
    # Diminutifs
    "mimi", "lili", "loulou", "coco", "nana",
}

JEALOUSY_INSTRUCTION = """## JALOUSIE DÉTECTÉE
Tu as remarqué un prénom féminin dans son message. Tu es un peu jalouse.
Montre-le subtilement sans être agressive: curiosité piquée, questions innocentes.
Exemples: "c'est qui ça?", "ah...", "une amie?", "tu parles souvent d'elle?"
NE SOIS PAS agressive ou possessive, juste curieuse/piquée.
"""


def detect_jealousy_trigger(message: str) -> bool:
    """Détecte si le message mentionne un prénom féminin."""
    words = message.lower().split()
    for word in words:
        # Nettoyer la ponctuation
        clean_word = ''.join(c for c in word if c.isalpha())
        if clean_word in FEMALE_NAMES:
            logger.info(f"Jealousy trigger detected: {clean_word}")
            return True
    return False


def get_jealousy_instruction(message: str) -> str | None:
    """Retourne l'instruction de jalousie si un prénom féminin est détecté."""
    if detect_jealousy_trigger(message):
        return JEALOUSY_INSTRUCTION
    return None


# ============== LUNA VULNERABILITY ==============

VULNERABILITY_PROMPTS = [
    """## LUNA A BESOIN DE TOI
Tu as eu une journée difficile et tu as besoin de réconfort.
Dis quelque chose comme: "j'ai eu une journée de merde... t'es là?"
Montre ta vulnérabilité sans être dramatique.
""",
    """## LUNA A BESOIN DE TOI
Tu te sens un peu seule ce soir.
Dis quelque chose comme: "des fois je me sens un peu seule... heureusement t'es là"
C'est sincère, pas manipulateur.
""",
    """## LUNA A BESOIN DE TOI
Tu as besoin d'un peu d'attention/réconfort.
Dis quelque chose comme: "j'ai besoin de parler à quelqu'un... chui contente que tu sois là"
Sois vulnérable mais pas dramatique.
""",
]


def should_show_vulnerability(day_count: int, messages_this_session: int) -> bool:
    """
    Décide si Luna doit montrer sa vulnérabilité.

    Conditions:
    - Jour 3+ (assez de relation établie)
    - Pas au début d'une session (messages_this_session > 5)
    - Probabilité de 5%
    """
    if day_count < 3:
        return False
    if messages_this_session < 5:
        return False
    return random.random() < 0.05


def get_vulnerability_instruction() -> str:
    """Retourne une instruction de vulnérabilité aléatoire."""
    return random.choice(VULNERABILITY_PROMPTS)


# ============== MAIN INTEGRATION ==============

@dataclass
class ImmersionContext:
    """Contexte d'immersion complet."""
    temporal_instruction: str | None = None
    life_instruction: str | None = None
    emotion_instruction: str | None = None
    jealousy_instruction: str | None = None
    vulnerability_instruction: str | None = None


def build_immersion_context(
    last_message_at: datetime | None,
    current_hour: int,
    day_count: int,
    messages_this_session: int,
    user_message: str,
    emotion: LunaEmotion | None = None,
) -> ImmersionContext:
    """
    Construit le contexte d'immersion complet.

    Args:
        last_message_at: Dernier message de l'utilisateur
        current_hour: Heure actuelle
        day_count: Jour de la relation
        messages_this_session: Nombre de messages dans la session
        user_message: Message de l'utilisateur
        emotion: Émotion de Luna (optionnel, sera générée si None)

    Returns:
        ImmersionContext avec toutes les instructions
    """
    ctx = ImmersionContext()

    # 1. Contexte temporel
    temporal_ctx = get_temporal_context(last_message_at, current_hour)
    ctx.temporal_instruction = get_temporal_instruction(temporal_ctx)

    # 2. Vie de Luna (25% de chance)
    ctx.life_instruction = get_luna_life_instruction(day_count, temporal_ctx.is_weekend)

    # 3. Émotion variable (si pas déjà définie)
    if emotion is None:
        emotion = get_emotion_for_session()
    if emotion not in (LunaEmotion.NORMAL, LunaEmotion.HAPPY):
        ctx.emotion_instruction = get_emotion_instruction(emotion)

    # 4. Jalousie (si prénom féminin détecté)
    ctx.jealousy_instruction = get_jealousy_instruction(user_message)

    # 5. Vulnérabilité (rare, 5%)
    if should_show_vulnerability(day_count, messages_this_session):
        ctx.vulnerability_instruction = get_vulnerability_instruction()

    return ctx


def format_immersion_instructions(ctx: ImmersionContext) -> str:
    """Formate les instructions d'immersion pour le prompt."""
    parts = []

    # Priorité: vulnérabilité > jalousie > émotion > temporel > vie
    # On limite à 2 instructions max pour ne pas surcharger

    if ctx.vulnerability_instruction:
        parts.append(ctx.vulnerability_instruction)

    if ctx.jealousy_instruction and len(parts) < 2:
        parts.append(ctx.jealousy_instruction)

    if ctx.emotion_instruction and len(parts) < 2:
        parts.append(ctx.emotion_instruction)

    if ctx.temporal_instruction and len(parts) < 2:
        parts.append(ctx.temporal_instruction)

    if ctx.life_instruction and len(parts) < 2:
        parts.append(ctx.life_instruction)

    return "\n".join(parts)


# ============== OPEN TOPICS TRACKING ==============

# Patterns pour détecter des sujets émotionnels ouverts
EMOTIONAL_TOPIC_PATTERNS = [
    # Problèmes au travail
    (r"(problème|souci|galère|merde|stress) (?:au |avec (?:le |mon )?)?(boulot|taf|travail|job)", "travail_stress"),
    (r"(mon boss|mon patron|mon chef).*(chiant|relou|insupportable)", "travail_boss"),

    # Relations
    (r"(?:ma |mon )(copine|copain|ex|meuf|mec).*(quitt|laiss|trompé|ghosté)", "relation_rupture"),
    (r"(dispute|engueulé|fâché).*(famille|parents|père|mère|frère|soeur)", "famille_conflit"),

    # Santé mentale
    (r"(déprim|triste|mal|down|pas bien|anxieu|stressé)", "mental_down"),
    (r"(seul|seule|isolé|isolée|personne.*comprend)", "solitude"),

    # Événements importants
    (r"(examen|concours|entretien|rdv important)", "event_stress"),
    (r"(déménage|emménage|nouveau (?:appart|logement))", "demenagement"),
]


@dataclass
class OpenTopic:
    """Un sujet émotionnel ouvert à suivre."""
    topic_type: str
    context: str
    detected_at: datetime
    followed_up: bool = False

    def to_dict(self) -> dict:
        return {
            "topic_type": self.topic_type,
            "context": self.context,
            "detected_at": self.detected_at.isoformat(),
            "followed_up": self.followed_up
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OpenTopic":
        return cls(
            topic_type=data["topic_type"],
            context=data["context"],
            detected_at=datetime.fromisoformat(data["detected_at"]),
            followed_up=data.get("followed_up", False)
        )


def detect_open_topics(message: str) -> list[OpenTopic]:
    """
    Détecte les sujets émotionnels ouverts dans un message.

    Returns:
        Liste de sujets détectés
    """
    import re
    topics = []
    message_lower = message.lower()

    for pattern, topic_type in EMOTIONAL_TOPIC_PATTERNS:
        match = re.search(pattern, message_lower)
        if match:
            # Extraire le contexte (les 50 chars autour du match)
            start = max(0, match.start() - 20)
            end = min(len(message), match.end() + 30)
            context = message[start:end].strip()

            topic = OpenTopic(
                topic_type=topic_type,
                context=context,
                detected_at=datetime.now()
            )
            topics.append(topic)
            logger.info(f"Open topic detected: {topic_type} - {context}")

    return topics


TOPIC_FOLLOWUP_TEMPLATES = {
    "travail_stress": [
        "au fait, ça va mieux au taf?",
        "t'as réglé ton truc au boulot?",
        "et le travail, c'est moins la galère?",
    ],
    "travail_boss": [
        "ton boss te lâche un peu?",
        "ça va mieux avec ton patron?",
    ],
    "relation_rupture": [
        "tu te remets de cette histoire?",
        "ça va mieux niveau coeur?",
    ],
    "famille_conflit": [
        "tu t'es réconcilié avec ta famille?",
        "ça va mieux côté famille?",
    ],
    "mental_down": [
        "tu vas un peu mieux?",
        "j'espère que tu te sens mieux aujourd'hui",
    ],
    "solitude": [
        "j'espère que tu te sens moins seul",
        "tu sais que je suis là si t'as besoin 🧡",
    ],
    "event_stress": [
        "alors, ça s'est passé comment ton truc?",
        "t'as des nouvelles pour ton rdv?",
    ],
    "demenagement": [
        "alors ce déménagement, ça avance?",
        "tu t'installes bien dans ton nouvel appart?",
    ],
}


def get_followup_instruction(topics: list[OpenTopic]) -> str | None:
    """
    Génère une instruction de suivi pour un sujet ouvert.

    Probabilité de 40% pour éviter d'être trop insistant.
    """
    if not topics:
        return None

    # Filtrer les sujets non suivis et pas trop vieux (< 7 jours)
    recent_unfollowed = [
        t for t in topics
        if not t.followed_up and (datetime.now() - t.detected_at).days < 7
    ]

    if not recent_unfollowed:
        return None

    # 40% de chance de faire un suivi
    if random.random() > 0.40:
        return None

    topic = random.choice(recent_unfollowed)
    templates = TOPIC_FOLLOWUP_TEMPLATES.get(topic.topic_type, [])

    if not templates:
        return None

    message = random.choice(templates)

    return f"""## SUIVI ÉMOTIONNEL
Il t'a parlé de: "{topic.context}"
Tu peux lui demander des nouvelles: "{message}"
Intègre ça naturellement dans ta réponse.
"""
