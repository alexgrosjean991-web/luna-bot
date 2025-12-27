"""
Subscription management for Luna Bot.

Handles:
- Checking subscription status
- Marking users as paid
- Future: MoonPay integration
"""

from typing import Optional

from core import get_logger

logger = get_logger(__name__)


# =============================================================================
# MODULE STATE
# =============================================================================

_pool = None


def set_pool(pool):
    """Set database pool."""
    global _pool
    _pool = pool


# =============================================================================
# SUBSCRIPTION CHECKS
# =============================================================================

async def is_subscriber(user_id) -> bool:
    """
    Check if user is a paying subscriber.

    Args:
        user_id: UUID of user in memory_users

    Returns:
        True if paid
    """
    if not _pool:
        logger.warning("Subscription check without pool - returning False")
        return False

    async with _pool.acquire() as conn:
        paid = await conn.fetchval("""
            SELECT paid FROM memory_relationships WHERE user_id = $1
        """, user_id)

    return bool(paid)


async def mark_paid(user_id, payment_id: Optional[str] = None) -> bool:
    """
    Mark user as paid subscriber.

    Args:
        user_id: UUID of user in memory_users
        payment_id: Optional payment reference

    Returns:
        True if successful
    """
    if not _pool:
        logger.error("Cannot mark paid without pool")
        return False

    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                UPDATE memory_relationships
                SET paid = TRUE
                WHERE user_id = $1
            """, user_id)

        logger.info(f"User {user_id} marked as paid (ref: {payment_id})")
        return True

    except Exception as e:
        logger.error(f"Failed to mark paid: {e}")
        return False


async def get_subscription_status(user_id) -> dict:
    """
    Get detailed subscription status.

    Returns:
        Dict with paid, payment_date, etc.
    """
    if not _pool:
        return {"paid": False}

    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT paid, updated_at
            FROM memory_relationships
            WHERE user_id = $1
        """, user_id)

    if not row:
        return {"paid": False}

    return {
        "paid": row["paid"],
        "since": row["updated_at"] if row["paid"] else None,
    }


# =============================================================================
# MOONPAY INTEGRATION (PLACEHOLDER)
# =============================================================================

async def create_moonpay_checkout(user_id, telegram_id: int) -> Optional[str]:
    """
    Create a MoonPay checkout URL for the user.

    TODO: Implement when MoonPay is ready

    Returns:
        Checkout URL or None
    """
    # Placeholder for future implementation
    logger.info(f"MoonPay checkout requested for {telegram_id}")
    return None


async def verify_moonpay_webhook(payload: dict, signature: str) -> bool:
    """
    Verify MoonPay webhook signature.

    TODO: Implement when MoonPay is ready

    Returns:
        True if valid
    """
    # Placeholder
    return False


async def process_moonpay_payment(payload: dict) -> bool:
    """
    Process a successful MoonPay payment.

    TODO: Implement when MoonPay is ready

    Returns:
        True if processed successfully
    """
    # Placeholder
    return False
