"""
Photos module for Luna Bot.

Usage:
    from photos import send_photo, check_access, PhotoCategory
"""

from photos.sender import send_photo, PhotoCategory
from photos.access import check_access, get_denial_message

__all__ = [
    "send_photo",
    "check_access",
    "get_denial_message",
    "PhotoCategory",
]
