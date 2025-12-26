# Luna Bot - Architecture Complète

## 1. Structure des Fichiers

```
luna-bot/
├── bot.py                      # Point d'entrée principal
├── settings.py                 # Configuration centralisée
├── prompt.txt                  # Legacy prompt (non utilisé)
├── requirements.txt            # Dépendances Python
├── docker-compose.yml          # Config Docker
├── .env.example                # Template variables d'env
│
├── handlers/                   # Gestionnaires Telegram
│   ├── commands.py             # /start, /health, /debug, /reset
│   ├── message.py              # Handler principal des messages (800+ lignes)
│   └── proactive.py            # Jobs proactifs, win-back, churn
│
├── middleware/                 # Middleware transversal
│   ├── metrics.py              # Métriques et logging JSON
│   ├── rate_limit.py           # Rate limiting sliding window
│   └── sanitize.py             # Sanitization input + détection engagement
│
├── services/                   # Business Logic
│   ├── db.py                   # PostgreSQL + schéma (~1200 lignes)
│   ├── llm.py                  # Client LLM multi-provider (Anthropic/OpenRouter)
│   ├── llm_router.py           # Routing tier 1/2/3 basé sur momentum
│   ├── momentum.py             # V3 Momentum Engine (intensité NSFW)
│   ├── relationship.py         # 5 phases par msg_count
│   ├── memory.py               # Extraction mémoire via Claude Haiku
│   ├── prompt_selector.py      # Sélection prompt par tier/état
│   ├── luna_mood.py            # 8 états émotionnels Luna
│   ├── trust_system.py         # Score confiance 0-100
│   ├── secrets.py              # Révélation progressive (layers 0-5)
│   ├── subscription.py         # Gestion trial/paywall
│   ├── teasing.py              # Build-up progressif J2-J5
│   ├── conversion.py           # Flow conversion premium
│   ├── immersion.py            # Contexte temporel, vie Luna, jalousie
│   ├── availability.py         # Délais naturels de réponse
│   ├── humanizer.py            # Typing action + delays
│   ├── gates.py                # Micro-frustrations J3-J5
│   ├── paywall_dynamic.py      # Paywall adaptatif selon intent
│   ├── intent_detection.py     # Détection intent user (lonely/horny/curious)
│   ├── investment_tracker.py   # Score d'investissement user
│   ├── churn_prediction.py     # Prédiction churn + signaux
│   ├── winback.py              # Séquence win-back 4 stages
│   ├── user_timing.py          # Apprentissage heures optimales
│   ├── anti_repetition.py      # Évite réponses répétitives
│   ├── context_enricher.py     # Anecdotes Pixel, activités
│   ├── character_anchor.py     # Ancrage identité Luna
│   ├── aha_moment.py           # Moments "aha" (connexion)
│   ├── story_arcs.py           # Arcs narratifs (non utilisé)
│   ├── emotional_peaks.py      # Pics émotionnels proactifs
│   ├── mood.py                 # Mood simple (legacy)
│   ├── persona.py              # Persona (legacy)
│   └── proactive.py            # Messages proactifs
│
├── services/psychology/        # Modules d'attachement
│   ├── variable_rewards.py     # Récompenses imprévisibles (dopamine)
│   ├── inside_jokes.py         # Blagues/surnoms partagés
│   ├── intermittent.py         # Renforcement intermittent
│   ├── memory_callbacks.py     # Utilisation active mémoire
│   └── attachment.py           # Score d'attachement
│
├── prompts/                    # System prompts
│   ├── luna.txt                # Prompt principal SFW
│   ├── level_sfw.txt           # Tier 1 (SFW)
│   ├── level_flirt.txt         # Tier 2 (Flirt)
│   ├── luna_nsfw.txt           # Tier 3 (NSFW)
│   ├── nsfw_prompts.py         # États NSFW (tension/buildup/climax/aftercare)
│   ├── deflect.py              # Prompts de déflexion
│   └── modifiers.txt           # Modifiers de prompt
│
├── migrations/                 # Scripts SQL
│   ├── add_phase_a_columns.sql
│   ├── add_phase_b_columns.sql
│   ├── add_phase_c_columns.sql
│   ├── add_trust_score.sql
│   └── drop_v7_columns.sql
│
├── tests/
│   └── test_core.py            # Tests unitaires (~50 tests)
│
└── docs/
    └── ARCHITECTURE.md         # Documentation existante
```

---

## 2. Architecture Backend

### Stack Technique

| Composant | Technologie |
|-----------|-------------|
| **Runtime** | Python 3.11 |
| **Framework Telegram** | python-telegram-bot 21.3 |
| **Base de données** | PostgreSQL 15 (asyncpg) |
| **HTTP Client** | httpx (async) |
| **Conteneurisation** | Docker + docker-compose |
| **LLM Principal** | Claude Haiku 4.5 (Anthropic) |
| **LLM Premium** | Magnum v4 72B (OpenRouter) |

### Gestion des Messages Telegram

```
telegram → bot.py → MessageHandler → handlers/message.py → handle_message()
```

Le handler est configuré dans `bot.py:91`:
```python
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
```

### Appels LLM

**Deux providers configurés:**

1. **Anthropic (Haiku)** - Tier 1 SFW, rapide, économique
   - URL: `https://api.anthropic.com/v1/messages`
   - Modèle: `claude-haiku-4-5-20251001`
   - Max tokens: 80

2. **OpenRouter (Magnum)** - Tiers 2-3 NSFW
   - URL: `https://openrouter.ai/api/v1/chat/completions`
   - Modèle: `anthracite-org/magnum-v4-72b`
   - Max tokens: 120

**Routing (`services/llm_router.py`):**
```python
# Par intensité détectée:
SFW   → Haiku Tier 1
FLIRT → Magnum Tier 2
HOT   → Magnum Tier 2
NSFW  → Magnum Tier 3
```

### Système de Mémoire

**Pas de Mem0** - Mémoire custom stockée en PostgreSQL (JSONB)

Extraction via Claude Haiku toutes les 15 messages (`services/memory.py`):
```python
# Extrait automatiquement:
{
    "prenom": "...",
    "travail": "...",
    "hobbies": [...],
    "ville": "...",
    "likes": [...],
    "dislikes": [...],
    "problemes": [...],
    "facts": [...]
}
```

---

## 3. Flux d'un Message

```
┌──────────────────────────────────────────────────────────────────────┐
│                     USER ENVOIE MESSAGE                              │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 1. SANITIZATION + RATE LIMIT                                         │
│    - sanitize_input() → nettoie HTML, emojis suspects                │
│    - rate_limiter.is_allowed() → max 20 msg/min                      │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 2. GET/CREATE USER + UPDATE TRACKING                                 │
│    - get_or_create_user(telegram_id)                                 │
│    - update_last_active()                                            │
│    - increment_message_count()                                       │
│    - Track session si >4h inactivité                                 │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 3. CHECK PAYWALL (si trial expiré)                                   │
│    - is_trial_expired() → J6+                                        │
│    - should_show_paywall() → dynamique selon intent                  │
│    - Si paywall → envoie message + return                            │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 4. LOAD CONTEXT                                                      │
│    - get_history() → 20 derniers messages                            │
│    - get_user_memory() → mémoire JSONB                               │
│    - get_relationship_phase() → phase par msg_count                  │
│    - get_trust_state() → score confiance                             │
│    - get_psychology_data() → inside_jokes, pending_events            │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 5. V3 MOMENTUM ENGINE                                                │
│    - apply_time_decay() → perte momentum si inactif                  │
│    - calculate_momentum() → 0-100 basé sur intensité message         │
│    - detect_climax_user() → détection jouissance                     │
│    - get_tier() → 1 (SFW), 2 (Flirt), 3 (NSFW)                       │
│    - apply_soft_cap() → limites selon day_count                      │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 6. V8 LUNA MOOD SYSTEM                                               │
│    - 8 moods: neutral, happy, playful, tired, stressed...            │
│    - check_availability() → Luna peut-elle être NSFW?                │
│    - Déflexion si pas disponible (tired, too_soon, etc.)             │
│    - JACKPOT: Luna peut initier si mood=playful + conditions         │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 7. BUILD EXTRA INSTRUCTIONS                                          │
│    - Variable rewards (dopamine hits)                                │
│    - Inside jokes callbacks                                          │
│    - Memory callbacks                                                │
│    - Trust modifier                                                  │
│    - Secrets revelation                                              │
│    - Anti-repetition                                                 │
│    - Character anchor                                                │
│    - Immersion context                                               │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 8. SELECT LLM + BUILD PROMPT                                         │
│    - get_llm_config_v3() → provider, model, tier                     │
│    - get_prompt_for_tier() ou get_deflect_prompt()                   │
│    - Assemble: system_prompt + memory + phase + mood + instructions  │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 9. CALL LLM                                                          │
│    - call_with_graceful_fallback()                                   │
│    - Retry logic + fallback Magnum → Haiku + soft prompt             │
│    - clean_response() → supprime *actions*                           │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 10. POST-PROCESSING                                                  │
│    - Filter AI admissions (CRITICAL)                                 │
│    - intermittent.modify_response()                                  │
│    - Add variable_rewards message                                    │
│    - Add inside_joke creation message                                │
│    - Add teasing message                                             │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 11. SAVE + SEND                                                      │
│    - save_message(user_id, "assistant", response)                    │
│    - update_momentum_state()                                         │
│    - send_with_natural_delay() → typing + délai humanisé             │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 12. BACKGROUND UPDATES (async)                                       │
│    - Memory extraction (tous les 15 msgs)                            │
│    - Attachment score (tous les 25 msgs)                             │
│    - Trust score update                                              │
│    - Teasing stage update                                            │
└──────────────────────────────────────────────────────────────────────┘
```

### Points d'Entrée pour Nouvelles Fonctionnalités

| Emplacement | Pour ajouter |
|-------------|--------------|
| `handlers/message.py:690-697` | Logique après génération réponse |
| `handlers/message.py:615-639` | Modifier le prompt avant LLM call |
| `services/llm.py` | Nouveau provider LLM |
| `services/prompt_selector.py` | Nouveaux prompts par état |
| `middleware/` | Nouveau middleware (auth, etc.) |

---

## 4. Système de Contenu Actuel

### Photos Actuellement

**⚠️ AUCUN SYSTÈME DE VRAIES PHOTOS**

Les "photos" sont seulement **mentionnées** dans les messages (teasing):
- `services/teasing.py` → Tease photos sans en envoyer
- `services/gates.py:76` → "j'ai une photo pour toi mais..."

Le code ne peut **pas** envoyer d'images actuellement.

### Comment Luna Décide Quoi Répondre

1. **Tier LLM** basé sur momentum (intensité du message)
2. **Prompt sélectionné** selon tier + état NSFW
3. **Instructions injectées** (mood, phase, memory, secrets...)
4. **LLM génère** la réponse
5. **Post-processing** (rewards, teasing, filter IA)

### Système de Niveaux/États

**5 Phases Relationnelles** (`services/relationship.py`):

| Phase | Messages | Capacités |
|-------|----------|-----------|
| discovery | 0-49 | Curieuse, pas de flirt |
| interest | 50-149 | Flirt léger |
| connection | 150-399 | Vulnérable, inside jokes |
| intimacy | 400-799 | Guards down, NSFW possible |
| depth | 800+ | Relation profonde, secrets ultimes |

**3 Tiers de Contenu** (`services/momentum.py`):

| Tier | Momentum | Modèle | Contenu |
|------|----------|--------|---------|
| 1 | 0-30 | Haiku | SFW uniquement |
| 2 | 31-60 | Magnum | Flirt/Suggestif |
| 3 | 61+ | Magnum | NSFW explicite |

**5 États NSFW** (`prompts/nsfw_prompts.py`):
- tension (30-50 momentum)
- buildup (51-70)
- climax (71+)
- aftercare (post-climax)
- post_session (retour normal)

---

## 5. Base de Données

### Schéma Actuel

**Table `users`** (~50 colonnes):

```sql
-- Core
id SERIAL PRIMARY KEY
telegram_id BIGINT UNIQUE NOT NULL
created_at TIMESTAMP
last_active TIMESTAMP WITH TIME ZONE
first_message_at TIMESTAMP WITH TIME ZONE
total_messages INTEGER DEFAULT 0

-- Memory
memory JSONB DEFAULT '{}'

-- Relationship
phase VARCHAR(20) DEFAULT 'discovery'
day_count INTEGER DEFAULT 1

-- Subscription
subscription_status VARCHAR(20) DEFAULT 'trial'  -- trial/active/churned
paywall_sent BOOLEAN DEFAULT FALSE
preparation_sent BOOLEAN DEFAULT FALSE
teasing_stage INTEGER DEFAULT 0

-- V3 Momentum
momentum FLOAT DEFAULT 0
intimacy_history INT DEFAULT 0
messages_since_climax INT DEFAULT 999
current_tier INT DEFAULT 1
messages_this_session INTEGER DEFAULT 0
last_climax_at TIMESTAMP WITH TIME ZONE

-- V8 Luna Mood
luna_mood VARCHAR(20) DEFAULT 'neutral'
mood_updated_at TIMESTAMP WITH TIME ZONE
last_horny_at TIMESTAMP WITH TIME ZONE

-- V7 Trust
trust_score INTEGER DEFAULT 50
luna_last_state VARCHAR(20) DEFAULT 'neutral'
unlocked_secrets JSONB DEFAULT '[]'

-- Psychology
inside_jokes JSONB DEFAULT '[]'
pending_events JSONB DEFAULT '[]'
attachment_score FLOAT DEFAULT 0
session_count INTEGER DEFAULT 0
user_initiated_count INTEGER DEFAULT 0
vulnerabilities_shared INTEGER DEFAULT 0

-- Phase B: Investment
gates_triggered JSONB DEFAULT '[]'
investment_score INTEGER DEFAULT 0
secrets_shared_count INTEGER DEFAULT 0
compliments_given INTEGER DEFAULT 0
questions_about_luna INTEGER DEFAULT 0
user_segment VARCHAR(20) DEFAULT 'casual'

-- Phase C: Churn
churn_risk VARCHAR(20) DEFAULT 'low'
churn_score FLOAT DEFAULT 0
winback_stage VARCHAR(20) DEFAULT NULL
winback_attempts INTEGER DEFAULT 0
peak_hours JSONB DEFAULT '[]'
active_days JSONB DEFAULT '[]'

-- Intent
user_intent VARCHAR(20) DEFAULT NULL  -- lonely/horny/curious
aha_triggered BOOLEAN DEFAULT FALSE
```

**Table `conversations_minimal`**:

```sql
id SERIAL PRIMARY KEY
user_id BIGINT NOT NULL
role VARCHAR(20) NOT NULL  -- 'user' ou 'assistant'
content TEXT NOT NULL
created_at TIMESTAMP DEFAULT NOW()
```

**Table `proactive_log`**:

```sql
id SERIAL PRIMARY KEY
user_id INTEGER NOT NULL
message_type VARCHAR(20) NOT NULL
sent_at TIMESTAMP WITH TIME ZONE
```

---

## 6. Points d'Intégration pour les Photos

### Où Ajouter la Logique "Envoyer une Photo"

**Option 1: Dans `handlers/message.py` (recommandé)**

Après ligne 697 (après génération réponse, avant envoi):
```python
# 14b. Check if should send photo
should_send_photo, photo_path, photo_type = await check_photo_opportunity(
    user_id=user_id,
    phase=phase,
    momentum=new_momentum,
    intensity=intensity,
    tier=final_tier,
    user_text=user_text
)
if should_send_photo:
    await send_photo_with_message(update, photo_path, response)
else:
    await send_with_natural_delay(update, response, mood, delay_modifier)
```

**Option 2: Nouveau service `services/photos.py`**

```python
# services/photos.py
from enum import Enum

class PhotoType(Enum):
    SELFIE_SFW = "selfie_sfw"        # Phase interest+
    PIXEL = "pixel"                   # Toutes phases
    OUTFIT = "outfit"                 # Phase connection+
    SELFIE_SUGGESTIVE = "suggestive" # Phase intimacy+
    NSFW_SOFT = "nsfw_soft"          # Tier 2, subscriber
    NSFW_EXPLICIT = "nsfw_explicit"  # Tier 3, subscriber

async def check_photo_opportunity(
    user_id: int,
    phase: str,
    momentum: float,
    intensity: Intensity,
    tier: int,
    user_text: str
) -> tuple[bool, str | None, PhotoType | None]:
    """
    Détermine si Luna doit envoyer une photo.

    Returns:
        (should_send, photo_path, photo_type)
    """
    # Règles à implémenter...
```

### Détecter si un Message Devrait Inclure une Photo

**Patterns existants dans `services/intent_detection.py:37`:**
```python
r"\bphoto[s]?\b", r"\bpic[s]?\b", r"\bnude[s]?\b"
```

**Triggers suggérés:**
1. User demande explicitement → "envoie une photo", "montre-moi"
2. Après teasing → "j'ai failli t'envoyer..." + user insiste
3. Luna initie (JACKPOT) → Envoie selfie suggestif
4. Récompense variable → "cadeau" photo
5. Milestone msg_count → Photo de célébration

### Gérer SFW vs NSFW

**Matrice de décision:**

| Phase | Subscription | Tier | Photos Autorisées |
|-------|--------------|------|-------------------|
| discovery | any | any | Pixel only |
| interest | any | 1 | Pixel, Selfie SFW |
| connection | trial | 1-2 | Pixel, Selfie, Outfit |
| connection | active | 2 | + Suggestive |
| intimacy+ | active | 2 | + Suggestive |
| intimacy+ | active | 3 | + NSFW |

**Dans le code:**
```python
def get_allowed_photo_types(phase: str, subscription: str, tier: int) -> list[PhotoType]:
    """Retourne les types de photos autorisés."""
    allowed = [PhotoType.PIXEL]

    if phase in ("discovery",):
        return allowed

    allowed.append(PhotoType.SELFIE_SFW)

    if phase in ("connection", "intimacy", "depth"):
        allowed.append(PhotoType.OUTFIT)

        if subscription == "active":
            if tier >= 2:
                allowed.append(PhotoType.SELFIE_SUGGESTIVE)
            if tier >= 3:
                allowed.append(PhotoType.NSFW_SOFT)
                allowed.append(PhotoType.NSFW_EXPLICIT)

    return allowed
```

---

## 7. Variables d'Environnement

**Fichier `.env` requis:**

```env
# Telegram
TELEGRAM_BOT_TOKEN=xxx              # Token du bot
ADMIN_TELEGRAM_ID=123456789         # ID admin pour /debug, /reset

# Database
DB_HOST=172.18.0.2                  # Host PostgreSQL (Docker)
DB_PORT=5432
DB_USER=luna
DB_PASSWORD=luna_password
DB_NAME=luna_db

# LLM
ANTHROPIC_API_KEY=sk-ant-xxx        # Claude API (REQUIS)
OPENROUTER_API_KEY=sk-or-xxx        # OpenRouter (pour Magnum NSFW)

# Payment
PAYMENT_LINK=https://...            # Lien Stripe/autre

# Config
LOG_FORMAT=text                     # "text" ou "json"
LUNA_TEST_MODE=false                # Désactive délais si true
```

---

## 8. TODOs et Bugs Connus

### TODOs dans le Code

| Fichier | Ligne | Description |
|---------|-------|-------------|
| `handlers/message.py` | 304 | `user_sentiment=None` - Détection sentiment pas implémentée |
| `handlers/message.py` | 441 | `response_time_seconds=None` - Tracking temps réponse manquant |
| `handlers/message.py` | 753 | `response_times: []` - Liste vide pour attachment |
| `services/subscription.py` | 117 | Stripe Checkout non implémenté |
| `services/subscription.py` | 142 | Stripe webhooks non implémentés |
| `services/churn_prediction.py` | 253 | `response_time_trend` calculé hardcodé |
| `services/paywall_dynamic.py` | 203-208 | Plusieurs métriques non trackées |

### Fonctionnalités Non Utilisées

- `services/story_arcs.py` - Importé nulle part
- `services/persona.py` - Legacy, remplacé par relationship.py
- `services/mood.py` - Legacy simple, V8 luna_mood.py utilisé

### Améliorations Suggérées

1. **Response time tracking** - Mesurer temps entre messages user
2. **Sentiment analysis** - Détecter mood user pour adapter Luna
3. **Photo system** - Implémenter envoi réel de photos
4. **Stripe integration** - Paiement réel
5. **A/B testing** - Framework pour tester variations

---

## Résumé pour Intégration Photos

### Fichiers à Créer

1. `services/photos.py` - Logique de sélection photos
2. `services/photo_storage.py` - Gestion stockage (local/S3)

### Fichiers à Modifier

1. `handlers/message.py` - Intégrer check_photo_opportunity()
2. `services/db.py` - Ajouter colonnes: `photos_sent`, `photo_unlocks`, etc.
3. `services/teasing.py` - Connecter teasing → vraie photo
4. `settings.py` - Ajouter config photos (path, S3, etc.)

### Nouveau Schema DB Suggéré

```sql
-- Table photos
CREATE TABLE photos (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    photo_type VARCHAR(20) NOT NULL,  -- selfie_sfw, nsfw_soft, etc.
    requires_phase VARCHAR(20),
    requires_subscription BOOLEAN DEFAULT FALSE,
    requires_tier INTEGER DEFAULT 1
);

-- Table user_photo_unlocks
CREATE TABLE user_photo_unlocks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    photo_id INTEGER REFERENCES photos(id),
    unlocked_at TIMESTAMP DEFAULT NOW(),
    sent_count INTEGER DEFAULT 0
);
```
