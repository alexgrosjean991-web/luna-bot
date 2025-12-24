"""Input sanitization for Luna Bot."""

MAX_MESSAGE_LENGTH = 2000


def sanitize_input(text: str | None) -> str | None:
    """Valide et nettoie l'entree utilisateur."""
    if not text:
        return None

    # Limiter la longueur
    text = text[:MAX_MESSAGE_LENGTH]

    # Supprimer caracteres de controle (sauf newlines)
    text = ''.join(c for c in text if c.isprintable() or c in '\n\r')

    return text.strip() or None


def detect_engagement_signal(text: str) -> int:
    """Detecte les signaux d'engagement positif pour le teasing stage.

    Returns: 0 (neutre), 1 (engagement leger), 2 (engagement fort)
    """
    text_lower = text.lower()

    # Signaux forts (+2): flirt explicite, compliments, enthousiasme
    strong_signals = [
        'j\'adore', 'trop belle', 'magnifique', 'canon', 'sublime',
        't\'es incroyable', 'tu me plais', 'j\'ai envie', 'tu me manques',
        'je kiffe', 'trop mignonne', 'j\'aime trop', 'tu me rends fou',
        '\U0001f60d', '\U0001f970', '\U0001f618', '\u2764\ufe0f', '\U0001f495', '\U0001f525'
    ]
    for signal in strong_signals:
        if signal in text_lower:
            return 2

    # Signaux legers (+1): interet, questions personnelles, positivite
    light_signals = [
        'tu fais quoi', 'raconte', 'et toi', 'parle moi', 'dis moi',
        'c\'est cool', 'j\'aime bien', 'interessant', 'haha', 'mdr',
        '\U0001f60a', '\U0001f60f', '\U0001f648', '\U0001f48b'
    ]
    for signal in light_signals:
        if signal in text_lower:
            return 1

    return 0
