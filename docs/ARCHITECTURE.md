# Architecture Luna Bot

## Vue d'ensemble

Luna Bot est un chatbot Telegram GFE (Girlfriend Experience) avec:
- Systeme de momentum V3 pour escalade naturelle
- Systeme de mood V8 pour disponibilite NSFW variable
- Modules psychologiques pour optimisation de l'attachement

## Structure des fichiers

```
luna-bot/
├── bot.py                  # Point d'entree (107 lignes)
├── settings.py             # Configuration centralisee
├── handlers/
│   ├── commands.py         # /start, /health, /debug, /reset
│   ├── message.py          # Handler principal des messages
│   └── proactive.py        # Messages proactifs automatiques
├── middleware/
│   ├── metrics.py          # Metriques + JSON logging
│   ├── rate_limit.py       # Rate limiting (20 msg/min)
│   └── sanitize.py         # Validation des entrees
├── services/
│   ├── db.py               # PostgreSQL async (asyncpg)
│   ├── llm.py              # Appels LLM avec fallback
│   ├── llm_router.py       # Routage Haiku/Magnum par tier
│   ├── momentum.py         # Systeme V3 momentum
│   ├── luna_mood.py        # Systeme V8 mood
│   ├── prompt_selector.py  # Selection prompts par tier
│   └── psychology/         # Modules attachement
├── prompts/
│   ├── level_sfw.txt       # Prompt tier 1 (Haiku)
│   ├── level_flirt.txt     # Prompt tier 2 (Magnum)
│   └── luna_nsfw.txt       # Prompt tier 3 (Magnum NSFW)
└── tests/
    └── test_core.py        # 44 tests unitaires
```

---

## V3: Systeme Momentum

### Concept

Remplace le systeme de niveaux discrets (V7) par un momentum continu (0-100).
L'escalade se fait naturellement en fonction de l'intensite des messages.

### Intensites

| Intensite | Description | Exemples |
|-----------|-------------|----------|
| SFW | Conversation normale | "salut", "ca va?" |
| FLIRT | Compliments, seduction legere | "tu es belle", "j'aime ta voix" |
| HOT | Tension sexuelle | "j'ai envie de toi" |
| NSFW | Contenu explicite | Messages sexuels |

### Tiers

| Tier | Momentum | Modele | Usage |
|------|----------|--------|-------|
| 1 | 0-34 | Haiku | Conversation SFW |
| 2 | 35-64 | Magnum | Flirt/Tension |
| 3 | 65-100 | Magnum NSFW | Contenu explicite |

### Calcul du momentum

```python
# Gains par intensite
INTENSITY_GAINS = {
    SFW: 2,
    FLIRT: 8,
    HOT: 15,
    NSFW: 25
}

# Bonus de session (premiers messages)
session_bonus = max(0, 20 - messages_this_session * 2)

# Nouveau momentum
new_momentum = min(100, current + gain + session_bonus)
```

### Decay (retour a la normale)

- **Time decay**: -5 points/minute d'inactivite
- **SFW decay boost**: +10 points de decay si message SFW apres NSFW
- **Post-climax decay**: +30 points apres aftercare termine

### Etats NSFW (Tier 3)

| Etat | Condition | Comportement |
|------|-----------|--------------|
| tension | momentum 30-50 | Flirt suggestif, creer l'attente |
| buildup | momentum 51-70 | Intensite croissante |
| climax | momentum 71+ | Intense et emotionnel |
| aftercare | 0-3 msgs post-climax | Tendresse, attachement |
| post_session | 4-10 msgs post-climax | Retour naturel |

### Soft Caps

Au lieu de bloquer l'escalade, le systeme applique des "soft caps":
- `TEASE_PATIENCE`: "mmh pas si vite..."
- `GENTLE_SLOW`: Ralentir sans rejeter
- `SOFT_REDIRECT`: Rediriger doucement

**Principe: Luna ne rejette JAMAIS, elle tease ou deflecte.**

---

## V8: Systeme Luna Mood

### Concept

Luna a son propre mood qui evolue independamment.
Cela cree de la variabilite et des moments "jackpot".

### Moods

| Mood | Probabilite | Effet sur NSFW |
|------|-------------|----------------|
| normal | 60% | Disponibilite standard |
| playful | 20% | Plus receptive au flirt |
| tired | 10% | Deflecte doucement |
| romantic | 9% | Prefere l'intimite emotionnelle |
| horny | 1% | **JACKPOT**: Luna initie |

### Mise a jour du mood

- Toutes les 2-4 heures
- Cooldown "horny": 5 jours minimum entre deux
- Contexte: heure, temps depuis climax

### Disponibilite NSFW

```python
availability = base_availability(mood)
            + time_factor(hour)        # +0.1 nuit
            + climax_recovery(minutes) # -0.5 si recent
            + momentum_factor(momentum)
```

Si `availability < 0.3` et user tente NSFW → deflection

### Types de deflection

| Type | Quand | Exemple |
|------|-------|---------|
| tired | Luna fatiguee | "jsuis crevee la..." |
| romantic | Prefere tendresse | "viens on se calme" |
| too_soon | Trop tot apres climax | "laisse moi respirer" |
| playful | Tease sans rejeter | "patience bb" |

### Luna Initiates (JACKPOT!)

Quand:
- mood == "horny"
- user n'est PAS explicite
- derniere fois > 48h

Luna envoie un message suggestif non sollicite.
Impact psychologique: reward imprevisible maximal.

---

## Routage LLM

### Providers

| Provider | Modele | Usage |
|----------|--------|-------|
| anthropic | claude-3-haiku | Tier 1 (SFW) |
| openrouter | sao10k/l3.3-euryale-70b | Tier 2-3 (NSFW) |

### Graceful Degradation

```
Magnum NSFW fail
    ↓
Magnum censored → Haiku + soft prompt
    ↓
Haiku fail → Natural exit message
```

### Cost Optimization

- Subscribers: Haiku pour SFW (meme si momentum eleve)
- Trial: Magnum pour teasing (conversion)

---

## Base de donnees

### Table `users`

```sql
-- Identite
id, telegram_id, memory (JSONB)

-- Session tracking
messages_this_session, last_climax_at

-- V3 Momentum
momentum, current_tier, intimacy_history, messages_since_climax

-- V8 Luna Mood
luna_mood, mood_updated_at, last_horny_at

-- Subscription
subscription_status, paywall_sent, premium_preview_count
```

### Colonnes supprimees (V7 legacy)

- `current_level` → remplace par `current_tier`
- `cooldown_remaining` → remplace par `messages_since_climax`
- `messages_since_level_change` → plus utilise

---

## Modules Psychologiques

### Variable Rewards (services/psychology/variable_rewards.py)

Recompenses imprevisibles pour creer des pics de dopamine:
- VULNERABILITY_SHARE: Luna partage une vulnerabilite
- SPECIAL_TREATMENT: "tu es different des autres"

### Inside Jokes (services/psychology/inside_jokes.py)

References partagees uniques a la relation:
- Detection d'opportunites dans les messages
- Callbacks reguliers pour renforcer le lien

### Intermittent Reinforcement (services/psychology/intermittent.py)

Disponibilite variable:
- Affection variable selon le contexte
- Delais de reponse variables

### Attachment Tracker (services/psychology/attachment.py)

Score d'attachement (0-100) base sur:
- Frequence des sessions
- Vulnerabilites partagees
- Inside jokes crees
- Messages inities par l'utilisateur

---

## Tests

```bash
# Lancer tous les tests
pytest tests/test_core.py -v

# Tests specifiques
pytest tests/test_core.py::TestMomentumEngine -v
pytest tests/test_core.py::TestLunaMoodEngine -v
```

### Couverture

- Middleware: sanitize, rate_limit, metrics
- Services: momentum, luna_mood, llm_router, prompt_selector
- Handlers: admin auth

---

## Deploiement

### Docker

```bash
docker-compose up -d
docker logs -f luna_bot
```

### Migration DB

```bash
# Supprimer colonnes V7 legacy
psql -U luna -d luna_db -f migrations/drop_v7_columns.sql
```

### Variables d'environnement

Voir `.env.example` pour la liste complete.
