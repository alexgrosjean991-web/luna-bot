"""Memory system for Luna Bot."""

from .models import (
    init_memory_tables,
    UserFacts,
    RelationshipState,
    TimelineEvent,
    LunaState,
    MemoryContext,
    EventType,
    RelationshipStatus,
    TierThreshold,
)

from .crud import (
    set_pool,
    get_pool,
    get_user,
    get_user_by_id,
    create_user,
    get_or_create_user,
    update_user,
    update_user_state,
    get_user_state,
    get_relationship,
    update_relationship,
    increment_relationship,
    add_inside_joke,
    increment_day,
    add_event,
    get_hot_events,
    get_pinned_events,
    get_events_by_keywords,
    get_luna_said,
    get_events_by_type,
    update_event,
    find_similar_event,
    update_tiers,
    cleanup_old_cold_events,
)

from .coherence import (
    check_luna_coherence,
    check_user_contradiction,
    get_user_contradictions,
    resolve_contradiction,
    build_memory_reminder,
    build_dont_invent_reminder,
)

from .extraction import (
    set_api_key as set_extraction_api_key,
    extract_user_facts,
    extract_luna_said,
    extract_from_history,
)

from .retrieval import (
    get_memory_context,
    build_prompt_context,
    get_quick_context,
    get_onboarding_nudge,
)

__all__ = [
    # Models
    "init_memory_tables",
    "UserFacts",
    "RelationshipState",
    "TimelineEvent",
    "LunaState",
    "MemoryContext",
    "EventType",
    "RelationshipStatus",
    "TierThreshold",
    # CRUD
    "set_pool",
    "get_pool",
    "get_user",
    "get_user_by_id",
    "create_user",
    "get_or_create_user",
    "update_user",
    "update_user_state",
    "get_user_state",
    "get_relationship",
    "update_relationship",
    "increment_relationship",
    "add_inside_joke",
    "increment_day",
    "add_event",
    "get_hot_events",
    "get_pinned_events",
    "get_events_by_keywords",
    "get_luna_said",
    "get_events_by_type",
    "update_event",
    "find_similar_event",
    "update_tiers",
    "cleanup_old_cold_events",
    # Coherence
    "check_luna_coherence",
    "check_user_contradiction",
    "get_user_contradictions",
    "resolve_contradiction",
    "build_memory_reminder",
    "build_dont_invent_reminder",
    # Extraction
    "set_extraction_api_key",
    "extract_user_facts",
    "extract_luna_said",
    "extract_from_history",
    # Retrieval
    "get_memory_context",
    "build_prompt_context",
    "get_quick_context",
    "get_onboarding_nudge",
]
