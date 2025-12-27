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
    # V2: New types
    InsideJoke,
    CalendarDate,
    UserPatterns,
    LunaCurrentLife,
    WeeklySummary,
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
    # V2: Summaries
    add_summary,
    get_summaries,
    get_latest_summary,
    # V2: Calendar
    add_calendar_date,
    get_upcoming_dates,
    cleanup_past_dates,
    # V2: Luna life
    update_luna_life,
    get_luna_life,
    # V2: User patterns
    update_user_patterns,
    get_user_patterns,
    # V2: Inside jokes enhanced
    add_inside_joke_v2,
    get_inside_jokes_v2,
    # V2: Bulk
    get_all_active_users,
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
    extract_unified,  # V2: Single LLM call for all
    extract_user_facts,  # Legacy wrapper
    extract_luna_said,   # Legacy wrapper
    extract_from_history,
)

from .retrieval import (
    get_memory_context,
    build_prompt_context,
    get_quick_context,
    get_onboarding_nudge,
    get_compressed_context,  # V2: For long-term users
)

from .compression import (
    set_api_key as set_compression_api_key,
    run_weekly_compression,
    run_monthly_compression,
    schedule_compression_jobs,
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
    "InsideJoke",
    "CalendarDate",
    "UserPatterns",
    "LunaCurrentLife",
    "WeeklySummary",
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
    # V2: New CRUD
    "add_summary",
    "get_summaries",
    "get_latest_summary",
    "add_calendar_date",
    "get_upcoming_dates",
    "cleanup_past_dates",
    "update_luna_life",
    "get_luna_life",
    "update_user_patterns",
    "get_user_patterns",
    "add_inside_joke_v2",
    "get_inside_jokes_v2",
    "get_all_active_users",
    # Coherence
    "check_luna_coherence",
    "check_user_contradiction",
    "get_user_contradictions",
    "resolve_contradiction",
    "build_memory_reminder",
    "build_dont_invent_reminder",
    # Extraction
    "set_extraction_api_key",
    "extract_unified",       # V2: Single LLM call
    "extract_user_facts",    # Legacy
    "extract_luna_said",     # Legacy
    "extract_from_history",
    # Retrieval
    "get_memory_context",
    "build_prompt_context",
    "get_quick_context",
    "get_onboarding_nudge",
    "get_compressed_context",
    # Compression
    "set_compression_api_key",
    "run_weekly_compression",
    "run_monthly_compression",
    "schedule_compression_jobs",
]
