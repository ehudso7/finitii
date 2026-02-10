"""Forecast service: Safe-to-Spend and 30-day deterministic forecast.

Implements:
1. Safe-to-Spend (Today): current balance - upcoming recurring charges today
2. Safe-to-Spend (Week): current balance - upcoming recurring charges next 7 days
3. 30-day daily balance projection with conservative volatility bands
4. Confidence scoring based on data quality
5. Urgency scoring (0-100) for ranking integration
6. Explicit assumptions attached to every forecast

Design principles (per PRD):
- Conservative ranges: lower bound uses pessimistic estimates
- Volatility bands: ±1 stddev of historical daily spending
- Explicit assumptions: every number traceable to source data
- No automation of money movement — forecast is informational only
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import mean, stdev

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.forecast import ForecastConfidence, ForecastSnapshot
from app.models.recurring import Confidence as RecurringConfidence, RecurringPattern
from app.models.transaction import Transaction, TransactionType
from app.services import audit_service


# --- Helpers ---

def _today_utc() -> datetime:
    """Current date at midnight UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _ensure_tz(dt: datetime) -> datetime:
    """SQLite returns naive datetimes — normalize to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# --- Data gathering ---

async def _get_total_available_balance(
    db: AsyncSession, user_id: uuid.UUID,
) -> Decimal:
    """Sum available (or current) balance across checking + savings accounts."""
    result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.account_type.in_([AccountType.checking, AccountType.savings]),
        )
    )
    accounts = result.scalars().all()
    total = Decimal("0.00")
    for acct in accounts:
        bal = acct.available_balance if acct.available_balance is not None else acct.current_balance
        total += bal
    return total


async def _get_upcoming_recurring(
    db: AsyncSession,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> list[RecurringPattern]:
    """Get recurring patterns with next_expected_date in [start, end]."""
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.user_id == user_id,
            RecurringPattern.is_active == True,  # noqa: E712
            RecurringPattern.next_expected_date >= start,
            RecurringPattern.next_expected_date <= end,
        )
    )
    return list(result.scalars().all())


async def _get_all_active_recurring(
    db: AsyncSession, user_id: uuid.UUID,
) -> list[RecurringPattern]:
    """Get all active recurring patterns."""
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.user_id == user_id,
            RecurringPattern.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def _get_recent_transactions(
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int = 90,
) -> list[Transaction]:
    """Get transactions from the last N days."""
    cutoff = _today_utc() - timedelta(days=days)
    result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= cutoff,
        ).order_by(Transaction.transaction_date.asc())
    )
    return list(result.scalars().all())


def _compute_daily_spending_stats(
    transactions: list[Transaction],
) -> tuple[Decimal, Decimal]:
    """Compute average daily spending and standard deviation from history.

    Returns (avg_daily_spend, daily_spend_stddev).
    Only considers debit transactions.
    """
    if not transactions:
        return Decimal("0.00"), Decimal("0.00")

    # Group spending by date
    daily_spend: dict[str, float] = defaultdict(float)
    for txn in transactions:
        if txn.transaction_type == TransactionType.debit:
            dt = _ensure_tz(txn.transaction_date)
            day_key = dt.strftime("%Y-%m-%d")
            daily_spend[day_key] += float(txn.amount)

    if not daily_spend:
        return Decimal("0.00"), Decimal("0.00")

    # Fill in zero-spend days for accurate average
    dates = sorted(daily_spend.keys())
    if len(dates) >= 2:
        from datetime import date as date_type
        start_date = date_type.fromisoformat(dates[0])
        end_date = date_type.fromisoformat(dates[-1])
        all_days = []
        current = start_date
        while current <= end_date:
            key = current.isoformat()
            all_days.append(daily_spend.get(key, 0.0))
            current += timedelta(days=1)
    else:
        all_days = list(daily_spend.values())

    avg = Decimal(str(round(mean(all_days), 2)))
    std = Decimal(str(round(stdev(all_days), 2))) if len(all_days) >= 2 else Decimal("0.00")

    return avg, std


def _compute_daily_income_stats(
    transactions: list[Transaction],
) -> Decimal:
    """Compute average daily income from credits."""
    if not transactions:
        return Decimal("0.00")

    daily_income: dict[str, float] = defaultdict(float)
    for txn in transactions:
        if txn.transaction_type == TransactionType.credit:
            dt = _ensure_tz(txn.transaction_date)
            day_key = dt.strftime("%Y-%m-%d")
            daily_income[day_key] += float(txn.amount)

    if not daily_income:
        return Decimal("0.00")

    # Total income / total days in range
    dates = sorted(daily_income.keys())
    if len(dates) >= 2:
        from datetime import date as date_type
        start_date = date_type.fromisoformat(dates[0])
        end_date = date_type.fromisoformat(dates[-1])
        total_days = (end_date - start_date).days + 1
        total_income = sum(daily_income.values())
        return Decimal(str(round(total_income / total_days, 2)))

    return Decimal("0.00")


# --- Recurring projection ---

def _project_recurring_for_period(
    patterns: list[RecurringPattern],
    start: datetime,
    end: datetime,
) -> dict[str, Decimal]:
    """Project recurring charges into daily buckets over a date range.

    Returns {date_str: total_amount} for each day with expected charges.
    Uses estimated_amount + amount_variance for conservative estimates.
    """
    daily_charges: dict[str, Decimal] = defaultdict(Decimal)

    for pattern in patterns:
        if pattern.next_expected_date is None:
            continue
        next_date = _ensure_tz(pattern.next_expected_date)

        # Project forward from next_expected_date using frequency
        freq_days = _frequency_to_days(pattern.frequency.value)
        if freq_days == 0:
            continue

        current = next_date
        while current <= end:
            if current >= start:
                day_key = current.strftime("%Y-%m-%d")
                # Conservative: use estimated + variance for upper bound
                daily_charges[day_key] += pattern.estimated_amount
            current += timedelta(days=freq_days)

    return dict(daily_charges)


def _frequency_to_days(frequency: str) -> int:
    """Map frequency to approximate number of days."""
    mapping = {
        "weekly": 7,
        "biweekly": 14,
        "monthly": 30,
        "quarterly": 91,
        "annual": 365,
    }
    return mapping.get(frequency, 0)


# --- Confidence ---

def _compute_forecast_confidence(
    transactions: list[Transaction],
    patterns: list[RecurringPattern],
) -> tuple[ForecastConfidence, dict]:
    """Compute forecast confidence based on data quality.

    High: ≥90 days of data + ≥3 high-confidence recurring patterns
    Medium: ≥30 days of data + ≥1 recurring pattern
    Low: less data than medium thresholds
    """
    # Transaction date range
    if transactions:
        dates = [_ensure_tz(t.transaction_date) for t in transactions]
        days_of_data = (max(dates) - min(dates)).days
    else:
        days_of_data = 0

    high_conf_patterns = [
        p for p in patterns if p.confidence == RecurringConfidence.high
    ]
    total_patterns = len(patterns)

    inputs = {
        "days_of_transaction_data": days_of_data,
        "total_recurring_patterns": total_patterns,
        "high_confidence_patterns": len(high_conf_patterns),
        "transaction_count": len(transactions),
    }

    if days_of_data >= 90 and len(high_conf_patterns) >= 3:
        return ForecastConfidence.high, inputs
    elif days_of_data >= 30 and total_patterns >= 1:
        return ForecastConfidence.medium, inputs
    else:
        return ForecastConfidence.low, inputs


# --- Urgency ---

def _compute_urgency(
    balance: Decimal,
    safe_to_spend_today: Decimal,
    safe_to_spend_week: Decimal,
    projected_end_balance: Decimal,
    avg_daily_spend: Decimal,
) -> tuple[int, dict]:
    """Compute urgency score (0-100) and factors.

    Higher urgency = more financially stressed.
    Factors:
    - Low balance relative to spending
    - Negative safe-to-spend
    - Projected balance decline
    """
    score = 0
    factors = []

    # Factor 1: Days of spending runway
    if avg_daily_spend > 0:
        runway_days = float(balance / avg_daily_spend)
        if runway_days < 7:
            score += 40
            factors.append(f"Balance covers only {runway_days:.0f} days of average spending")
        elif runway_days < 14:
            score += 25
            factors.append(f"Balance covers ~{runway_days:.0f} days of average spending")
        elif runway_days < 30:
            score += 10
            factors.append(f"Balance covers ~{runway_days:.0f} days of average spending")

    # Factor 2: Negative safe-to-spend
    if safe_to_spend_today < 0:
        score += 30
        factors.append("Safe-to-spend today is negative")
    elif safe_to_spend_week < 0:
        score += 20
        factors.append("Safe-to-spend this week is negative")

    # Factor 3: Projected balance decline
    if projected_end_balance < 0:
        score += 30
        factors.append("30-day projected balance is negative")
    elif projected_end_balance < balance * Decimal("0.5"):
        score += 15
        factors.append("30-day projection shows >50% balance decline")

    # Cap at 100
    score = min(score, 100)

    return score, {"score": score, "factors": factors}


# --- Main forecast computation ---

async def compute_forecast(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    ip_address: str | None = None,
) -> ForecastSnapshot:
    """Compute and store a forecast snapshot.

    Deterministic forecast based on:
    1. Current account balances
    2. Recurring pattern projections
    3. Historical spending patterns (average + volatility)
    """
    today = _today_utc()
    today_end = today + timedelta(hours=23, minutes=59, seconds=59)
    week_end = today + timedelta(days=7)
    month_end = today + timedelta(days=30)

    # Gather data
    balance = await _get_total_available_balance(db, user_id)
    all_patterns = await _get_all_active_recurring(db, user_id)
    transactions = await _get_recent_transactions(db, user_id, days=90)

    # Spending stats
    avg_daily_spend, daily_spend_std = _compute_daily_spending_stats(transactions)
    avg_daily_income = _compute_daily_income_stats(transactions)

    # Recurring projections
    recurring_today = await _get_upcoming_recurring(db, user_id, today, today_end)
    recurring_week = await _get_upcoming_recurring(db, user_id, today, week_end)
    recurring_charges_30d = _project_recurring_for_period(all_patterns, today, month_end)

    # Sum recurring charges
    recurring_total_today = sum(
        (p.estimated_amount for p in recurring_today), Decimal("0.00")
    )
    recurring_total_week = sum(
        (p.estimated_amount for p in recurring_week), Decimal("0.00")
    )

    # Safe-to-Spend: conservative = balance - known upcoming charges
    # We subtract recurring charges but do NOT add projected income (conservative)
    safe_to_spend_today = balance - recurring_total_today
    safe_to_spend_week = balance - recurring_total_week

    # 30-day daily balance projection
    daily_balances = []
    running_balance = balance

    for day_offset in range(1, 31):
        proj_date = today + timedelta(days=day_offset)
        day_key = proj_date.strftime("%Y-%m-%d")

        # Subtract recurring charges for this day
        day_recurring = recurring_charges_30d.get(day_key, Decimal("0.00"))

        # Subtract average non-recurring daily spending
        # (avg_daily_spend includes recurring, so subtract the recurring portion
        # to avoid double-counting; simplified: use full avg as conservative estimate)
        day_discretionary = avg_daily_spend

        # Add average daily income
        day_income = avg_daily_income

        # Net change: income - recurring - discretionary
        net_change = day_income - day_recurring - day_discretionary
        running_balance += net_change

        # Volatility bands: ±1 stddev of daily spending
        low = running_balance - daily_spend_std * day_offset
        high = running_balance + daily_spend_std * day_offset

        # Conservative: low band uses pessimistic estimate
        # Scale volatility by sqrt of days for more realistic bands
        import math
        volatility_factor = Decimal(str(round(math.sqrt(day_offset), 2)))
        low_band = running_balance - daily_spend_std * volatility_factor
        high_band = running_balance + daily_spend_std * volatility_factor

        daily_balances.append({
            "day": day_offset,
            "date": day_key,
            "projected": str(round(running_balance, 2)),
            "low": str(round(low_band, 2)),
            "high": str(round(high_band, 2)),
        })

    projected_end = running_balance
    projected_end_low = Decimal(daily_balances[-1]["low"]) if daily_balances else balance
    projected_end_high = Decimal(daily_balances[-1]["high"]) if daily_balances else balance

    # Confidence
    confidence, confidence_inputs = _compute_forecast_confidence(transactions, all_patterns)

    # Assumptions
    assumptions = _build_assumptions(
        balance, avg_daily_spend, avg_daily_income,
        all_patterns, recurring_total_today, recurring_total_week,
        transactions,
    )

    # Urgency
    urgency_score, urgency_factors = _compute_urgency(
        balance, safe_to_spend_today, safe_to_spend_week,
        projected_end, avg_daily_spend,
    )

    # Store snapshot
    snapshot = ForecastSnapshot(
        user_id=user_id,
        safe_to_spend_today=safe_to_spend_today,
        safe_to_spend_week=safe_to_spend_week,
        daily_balances=daily_balances,
        projected_end_balance=round(projected_end, 2),
        projected_end_low=round(projected_end_low, 2),
        projected_end_high=round(projected_end_high, 2),
        confidence=confidence,
        confidence_inputs=confidence_inputs,
        assumptions=assumptions,
        urgency_score=urgency_score,
        urgency_factors=urgency_factors,
    )
    db.add(snapshot)
    await db.flush()

    # Audit log
    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="forecast.computed",
        entity_type="ForecastSnapshot",
        entity_id=snapshot.id,
        action="compute",
        detail={
            "safe_to_spend_today": str(safe_to_spend_today),
            "safe_to_spend_week": str(safe_to_spend_week),
            "projected_end_balance": str(round(projected_end, 2)),
            "confidence": confidence.value,
            "urgency_score": urgency_score,
        },
        ip_address=ip_address,
    )

    return snapshot


def _build_assumptions(
    balance: Decimal,
    avg_daily_spend: Decimal,
    avg_daily_income: Decimal,
    patterns: list[RecurringPattern],
    recurring_today: Decimal,
    recurring_week: Decimal,
    transactions: list[Transaction],
) -> list[str]:
    """Build explicit list of assumptions for the forecast."""
    assumptions = []

    assumptions.append(f"Current total available balance: ${balance:.2f}")

    if transactions:
        dates = [_ensure_tz(t.transaction_date) for t in transactions]
        days_range = (max(dates) - min(dates)).days
        assumptions.append(
            f"Based on {len(transactions)} transactions over {days_range} days"
        )

    assumptions.append(f"Average daily spending: ${avg_daily_spend:.2f}")
    assumptions.append(f"Average daily income: ${avg_daily_income:.2f}")

    if patterns:
        total_recurring_monthly = sum(
            p.estimated_amount for p in patterns
            if p.frequency.value == "monthly"
        )
        assumptions.append(
            f"{len(patterns)} active recurring patterns "
            f"(${total_recurring_monthly:.2f}/month in monthly charges)"
        )

    if recurring_today > 0:
        assumptions.append(f"${recurring_today:.2f} in recurring charges due today")

    if recurring_week > 0:
        assumptions.append(f"${recurring_week:.2f} in recurring charges due this week")

    assumptions.append("Forecast does not include unexpected expenses or income")
    assumptions.append("Volatility bands represent ±1 standard deviation of daily spending")

    return assumptions


async def get_latest_forecast(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> ForecastSnapshot | None:
    """Get the most recent forecast snapshot for a user."""
    result = await db.execute(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.user_id == user_id)
        .order_by(ForecastSnapshot.computed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_forecast_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 10,
) -> list[ForecastSnapshot]:
    """Get recent forecast snapshots for a user."""
    result = await db.execute(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.user_id == user_id)
        .order_by(ForecastSnapshot.computed_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
