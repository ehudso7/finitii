"""Merchant normalization service.

Normalizes raw merchant names from transaction descriptions:
- Strip trailing location/store numbers
- Strip whitespace, normalize case
- Merge known aliases (configurable mapping)
- Idempotent get-or-create

All merchant operations are audit-logged.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant
from app.services import audit_service

# Known merchant alias mapping: normalized_key -> canonical normalized name
# This is expanded as more merchants are encountered.
MERCHANT_ALIASES: dict[str, str] = {
    "amzn mktp us": "amazon",
    "amazon.com": "amazon",
    "amzn mktp": "amazon",
    "amazon prime": "amazon",
    "wal-mart": "walmart",
    "wm supercenter": "walmart",
    "mcdonald's": "mcdonalds",
    "mcdonalds": "mcdonalds",
    "google *": "google",
    "apple.com/bill": "apple",
}

# Regex patterns to strip from raw merchant names
_STRIP_PATTERNS = [
    r"\s*#\s*\d+.*$",       # Store numbers: "#1234 NYC"
    r"\s*\*\s*\w+.*$",      # Reference codes: "*AB1CD"
    r"\s+\d{3,}.*$",        # Trailing numeric IDs
    r"\s+(?:sq|sq\s*\*)\s*", # Square prefix
]

_STRIP_RE = re.compile("|".join(_STRIP_PATTERNS), re.IGNORECASE)


def normalize_name(raw_name: str) -> str:
    """Normalize a raw merchant name to a canonical form for matching.

    Steps:
    1. Strip whitespace
    2. Remove store numbers, reference codes, trailing numeric IDs
    3. Lowercase for matching
    4. Check alias table
    """
    cleaned = raw_name.strip()
    cleaned = _STRIP_RE.sub("", cleaned).strip()
    lowered = cleaned.lower()

    # Check aliases
    for alias_key, canonical in MERCHANT_ALIASES.items():
        if lowered.startswith(alias_key) or lowered == alias_key:
            return canonical

    return lowered


def to_display_name(normalized: str) -> str:
    """Convert normalized name to a display-friendly title case."""
    return normalized.replace("_", " ").title()


async def get_or_create_merchant(
    db: AsyncSession,
    raw_name: str,
    *,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> Merchant:
    """Find an existing merchant by normalized name, or create a new one.

    Idempotent: calling with the same raw name returns the same merchant.
    """
    normalized = normalize_name(raw_name)

    # Look up by normalized name
    result = await db.execute(
        select(Merchant).where(Merchant.normalized_name == normalized)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    # Create new merchant
    display = to_display_name(normalized)
    merchant = Merchant(
        raw_name=raw_name,
        normalized_name=normalized,
        display_name=display,
    )
    db.add(merchant)
    await db.flush()

    if user_id is not None:
        await audit_service.log_event(
            db,
            user_id=user_id,
            event_type="merchant.created",
            entity_type="Merchant",
            entity_id=merchant.id,
            action="create",
            detail={"raw_name": raw_name, "normalized_name": normalized},
            ip_address=ip_address,
        )

    return merchant
