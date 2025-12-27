"""
Luna Bot entry point.

Usage:
    python -m bot.main
"""

import asyncio
from datetime import time as dt_time

import asyncpg
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from core import get_logger, setup_logging
from config.settings import settings, validate_settings
from memory import (
    set_pool as set_memory_pool,
    set_extraction_api_key,
    set_compression_api_key,
    init_memory_tables,
    update_tiers,
    run_weekly_compression,
    run_monthly_compression,
)
from bot.handlers import (
    handle_start,
    handle_debug,
    handle_setpaid,
    handle_setday,
    handle_resetmsgs,
    handle_health,
    handle_message,
)
from bot.handlers import commands as cmd_module
from bot.handlers import messages as msg_module

logger = get_logger(__name__)


# =============================================================================
# DATABASE INIT
# =============================================================================

pool: asyncpg.Pool | None = None


async def init_db():
    """Initialize database and memory system."""
    global pool
    pool = await asyncpg.create_pool(
        **settings.DB_CONFIG,
        min_size=settings.DB_POOL_MIN,
        max_size=settings.DB_POOL_MAX,
    )

    # Set pool for handlers
    cmd_module.set_pool(pool)
    msg_module.set_pool(pool)

    # Init memory system
    set_memory_pool(pool)
    set_extraction_api_key(settings.OPENROUTER_API_KEY)
    set_compression_api_key(settings.OPENROUTER_API_KEY)
    await init_memory_tables(pool)

    # Create additional tables
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations_simple (
                id SERIAL PRIMARY KEY,
                user_id UUID REFERENCES memory_users(id),
                role VARCHAR(10) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_simple_user
            ON conversations_simple(user_id, created_at DESC)
        """)
        await conn.execute("""
            ALTER TABLE memory_relationships
            ADD COLUMN IF NOT EXISTS nsfw_gate_data JSON DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE memory_relationships
            ADD COLUMN IF NOT EXISTS message_count INTEGER DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE memory_relationships
            ADD COLUMN IF NOT EXISTS engagement_state JSON DEFAULT NULL
        """)
        await conn.execute("""
            ALTER TABLE memory_relationships
            ADD COLUMN IF NOT EXISTS paywall_shown BOOLEAN DEFAULT FALSE
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS proactive_tracking (
                user_id UUID PRIMARY KEY REFERENCES memory_users(id),
                proactive_count_today INTEGER DEFAULT 0,
                last_proactive_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                proactive_date DATE DEFAULT CURRENT_DATE
            )
        """)

    logger.info("Database initialized")


# =============================================================================
# JOBS
# =============================================================================

async def job_memory_tiers(context):
    """Hourly memory tier update."""
    try:
        count = await update_tiers()
        if count:
            logger.info(f"Memory tiers updated: {count}")
    except Exception as e:
        logger.error(f"Tier update error: {e}")


async def job_weekly_compression(context):
    """Weekly compression (Sundays 3am)."""
    try:
        logger.info("Running weekly compression...")
        stats = await run_weekly_compression()
        logger.info(f"Weekly compression done: {stats}")
    except Exception as e:
        logger.error(f"Weekly compression error: {e}")


async def job_monthly_compression(context):
    """Monthly compression (1st of month 4am)."""
    from datetime import datetime
    if datetime.now().day != 1:
        return
    try:
        logger.info("Running monthly compression...")
        stats = await run_monthly_compression()
        logger.info(f"Monthly compression done: {stats}")
    except Exception as e:
        logger.error(f"Monthly compression error: {e}")


async def job_daily_cleanup(context):
    """Daily DB cleanup (2am)."""
    try:
        async with pool.acquire() as conn:
            conv_deleted = await conn.fetchval("""
                WITH deleted AS (
                    DELETE FROM conversations_simple
                    WHERE created_at < NOW() - INTERVAL '90 days'
                    RETURNING id
                )
                SELECT COUNT(*) FROM deleted
            """)

            events_deleted = await conn.fetchval("""
                WITH deleted AS (
                    DELETE FROM memory_timeline
                    WHERE tier = 'cold'
                      AND pinned = FALSE
                      AND created_at < NOW() - INTERVAL '180 days'
                    RETURNING id
                )
                SELECT COUNT(*) FROM deleted
            """)

            if conv_deleted or events_deleted:
                logger.info(f"DB cleanup: {conv_deleted} convs, {events_deleted} events")

    except Exception as e:
        logger.error(f"DB cleanup error: {e}")


# =============================================================================
# APP FACTORY
# =============================================================================

def create_app() -> Application:
    """Create Telegram application."""
    app = Application.builder().token(settings.TELEGRAM_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("health", handle_health))
    app.add_handler(CommandHandler("debug", handle_debug))
    app.add_handler(CommandHandler("setpaid", handle_setpaid))
    app.add_handler(CommandHandler("setday", handle_setday))
    app.add_handler(CommandHandler("resetmsgs", handle_resetmsgs))

    # Message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Jobs
    app.job_queue.run_repeating(job_memory_tiers, interval=3600, first=300)
    app.job_queue.run_daily(job_weekly_compression, time=dt_time(3, 0), days=(6,))
    app.job_queue.run_daily(job_monthly_compression, time=dt_time(4, 0))
    app.job_queue.run_daily(job_daily_cleanup, time=dt_time(2, 0))

    return app


# =============================================================================
# RUN
# =============================================================================

async def run_bot():
    """Run the bot."""
    # Validate config
    errors = validate_settings()
    if errors:
        for e in errors:
            logger.error(f"Config error: {e}")
        raise SystemExit(1)

    # Init DB
    await init_db()

    # Create and run app
    app = create_app()

    logger.info(f"Luna Bot v{settings.BOT_VERSION} starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        if pool:
            await pool.close()


def main():
    """Entry point."""
    setup_logging(level=settings.LOG_LEVEL, json_format=settings.LOG_JSON)
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
