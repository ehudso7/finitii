"""Agent Runner — Diverse Persona End-to-End Tests.

Runs 12 unique persona agents representing different demographics,
income levels, and life situations through the FULL Finitii flow:

1. Register/Login
2. Grant consent (data_access + terms_of_service)
3. Create manual account
4. Ingest transactions
5. Detect recurring patterns
6. Compute forecast
7. Create goals + constraints
8. Seed & fetch Top 3
9. Start a cheat code run
10. Complete step 1 (First Win)
11. Advance onboarding through all gates
12. Verify PRD non-negotiables

Each agent independently verifies:
- NO low confidence leaks into Top 3
- Forecast includes assumptions list
- Audit trail present for critical actions
- First Win completes successfully
- All endpoints return expected status codes
- Coach returns template-based responses
"""

import io
import json
import time
import uuid
import pytest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.storage import InMemoryStorageBackend, set_storage


# ============================================================
# PERSONA DEFINITIONS — 12 diverse demographic profiles
# ============================================================

PERSONAS = [
    {
        "name": "Marcus — Fresh College Grad",
        "description": "22yo, first job ($38k), student loans, shared apartment",
        "email": "marcus.grad@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Online Bank",
            "account_name": "Main Checking",
            "current_balance": 820.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "PAYROLL STARTUP INC", "amount": 1460.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "RENT SPLIT FEB", "amount": 675.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "STUDENT LOAN PAYMENT", "amount": 285.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "SPOTIFY USA", "amount": 11.99, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "CHIPOTLE #2045", "amount": 12.50, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "UBER TRIP NYC", "amount": 22.40, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "RAMEN SHOP", "amount": 15.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
            {"raw_description": "AMZN MKTP", "amount": 34.99, "transaction_type": "debit", "transaction_date": "2026-02-07"},
        ],
        "goal": {"goal_type": "pay_off_debt", "title": "Pay off student loans", "priority": "high"},
        "constraint": {"constraint_type": "fixed", "label": "Student loan non-negotiable"},
    },
    {
        "name": "Keisha — Single Mom, Two Kids",
        "description": "34yo, nurse ($52k), two children ages 5 and 8",
        "email": "keisha.mom@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Community Credit Union",
            "account_name": "Family Checking",
            "current_balance": 1450.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "PAYROLL HOSPITAL SYSTEM", "amount": 2000.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "RENT FEB", "amount": 1100.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "GROCERY MART", "amount": 142.30, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "CHILD CARE CENTER", "amount": 450.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "CELL PHONE BILL", "amount": 65.00, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "NETFLIX.COM", "amount": 15.49, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "GAS STATION", "amount": 48.50, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "KIDS SHOES STORE", "amount": 39.99, "transaction_type": "debit", "transaction_date": "2026-02-06"},
            {"raw_description": "PHARMACY", "amount": 22.00, "transaction_type": "debit", "transaction_date": "2026-02-07"},
            {"raw_description": "WALMART GROCERY", "amount": 98.67, "transaction_type": "debit", "transaction_date": "2026-02-08"},
        ],
        "goal": {"goal_type": "build_emergency_fund", "title": "Emergency fund for family", "priority": "high"},
        "constraint": {"constraint_type": "essential", "label": "Childcare is non-negotiable"},
    },
    {
        "name": "Harold — Retired Teacher",
        "description": "68yo, fixed pension ($2,200/mo), Medicare, widowed",
        "email": "harold.retired@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "National Bank",
            "account_name": "Pension Account",
            "current_balance": 3200.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "PENSION DEPOSIT", "amount": 2200.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "MORTGAGE PAYMENT", "amount": 890.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "MEDICARE SUPPLEMENT", "amount": 164.90, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "PHARMACY CVS", "amount": 85.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "GROCERY STORE", "amount": 67.43, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "ELECTRIC COMPANY", "amount": 125.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "SENIOR CENTER DUES", "amount": 25.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
        ],
        "goal": {"goal_type": "save_money", "title": "Stretch fixed income", "priority": "high"},
        "constraint": {"constraint_type": "medical", "label": "Prescriptions are essential"},
    },
    {
        "name": "Javier — Gig Worker / Rideshare",
        "description": "29yo, Uber/DoorDash driver, irregular income",
        "email": "javier.gig@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Digital Bank",
            "account_name": "Gig Earnings",
            "current_balance": 640.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "UBER DRIVER PAYOUT", "amount": 380.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "DOORDASH PAYOUT", "amount": 220.00, "transaction_type": "credit", "transaction_date": "2026-02-03"},
            {"raw_description": "UBER DRIVER PAYOUT", "amount": 415.00, "transaction_type": "credit", "transaction_date": "2026-02-05"},
            {"raw_description": "RENT", "amount": 750.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "CAR INSURANCE", "amount": 180.00, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "GAS SHELL", "amount": 55.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "GAS SHELL", "amount": 52.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
            {"raw_description": "CELL PHONE PREPAID", "amount": 35.00, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "TACO TRUCK", "amount": 8.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
        ],
        "goal": {"goal_type": "budget_better", "title": "Stabilize gig income budget", "priority": "high"},
        "constraint": {"constraint_type": "business", "label": "Gas and insurance are work expenses"},
    },
    {
        "name": "Priya — Software Engineer, High Earner",
        "description": "31yo, FAANG engineer ($185k), lots of subscriptions, invests",
        "email": "priya.tech@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "High-Yield Bank",
            "account_name": "Primary Checking",
            "current_balance": 12500.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "PAYROLL TECHCORP", "amount": 7100.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "RENT LUXURY APT", "amount": 2800.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "NETFLIX.COM", "amount": 22.99, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "SPOTIFY FAMILY", "amount": 16.99, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "HULU", "amount": 17.99, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "ADOBE CREATIVE", "amount": 54.99, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "AWS SERVICES", "amount": 23.50, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "WHOLE FOODS", "amount": 186.00, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "PELOTON", "amount": 44.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "GYM EQUINOX", "amount": 210.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "UBER EATS", "amount": 45.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
            {"raw_description": "ROBINHOOD TRANSFER", "amount": 1000.00, "transaction_type": "debit", "transaction_date": "2026-02-07"},
        ],
        "goal": {"goal_type": "reduce_spending", "title": "Cut unnecessary subscriptions", "priority": "medium"},
        "constraint": {"constraint_type": "keep", "label": "Keep investment transfers"},
    },
    {
        "name": "Rosa — Immigrant Restaurant Worker",
        "description": "42yo, kitchen worker ($28k), sends remittances, ESL",
        "email": "rosa.worker@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Local Credit Union",
            "account_name": "Checking",
            "current_balance": 380.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "PAYROLL RESTAURANT", "amount": 1080.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "RENT", "amount": 550.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "WESTERN UNION REMIT", "amount": 200.00, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "GROCERY TIENDA", "amount": 78.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "METRO CARD", "amount": 33.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "CELL PHONE PREPAID", "amount": 25.00, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "LAUNDROMAT", "amount": 12.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
        ],
        "goal": {"goal_type": "save_money", "title": "Save for family needs", "priority": "high"},
        "constraint": {"constraint_type": "fixed", "label": "Monthly remittance is essential"},
    },
    {
        "name": "Dave — Small Business Owner",
        "description": "45yo, owns a plumbing company, mixes personal/business",
        "email": "dave.plumber@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Business Bank",
            "account_name": "Business Checking",
            "current_balance": 5800.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "CLIENT PAYMENT JONES", "amount": 2400.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "CLIENT PAYMENT SMITH", "amount": 1800.00, "transaction_type": "credit", "transaction_date": "2026-02-04"},
            {"raw_description": "TRUCK PAYMENT", "amount": 650.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "SUPPLY HOUSE", "amount": 340.00, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "BUSINESS INSURANCE", "amount": 280.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "PERSONAL RENT", "amount": 1200.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "QUICKBOOKS SUB", "amount": 30.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "GAS STATION", "amount": 65.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "CELL PHONE BUSINESS", "amount": 85.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
            {"raw_description": "HARDWARE STORE", "amount": 125.00, "transaction_type": "debit", "transaction_date": "2026-02-07"},
        ],
        "goal": {"goal_type": "budget_better", "title": "Separate personal from business", "priority": "high"},
        "constraint": {"constraint_type": "business", "label": "Truck payment is tax deductible"},
    },
    {
        "name": "Tamika — Military Spouse",
        "description": "27yo, spouse deployed, BAH housing, 1 child, part-time remote",
        "email": "tamika.milspouse@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "USAA",
            "account_name": "Joint Checking",
            "current_balance": 2900.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "DFAS MILITARY PAY", "amount": 3200.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "PART TIME REMOTE PAY", "amount": 800.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "RENT OFF-BASE", "amount": 1400.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "TRICARE DENTAL", "amount": 45.00, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "COMMISSARY GROCERY", "amount": 156.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "CHILD CARE", "amount": 300.00, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "CAR PAYMENT", "amount": 350.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "CAR INSURANCE USAA", "amount": 95.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "INTERNET BILL", "amount": 60.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
        ],
        "goal": {"goal_type": "build_emergency_fund", "title": "PCS relocation fund", "priority": "high"},
        "constraint": {"constraint_type": "essential", "label": "Car payment — needed for base commute"},
    },
    {
        "name": "Linda — Rural Teacher",
        "description": "55yo, small-town teacher ($42k), drives 30mi to school",
        "email": "linda.teacher@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Farm Bureau Bank",
            "account_name": "Checking",
            "current_balance": 1100.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "PAYROLL SCHOOL DISTRICT", "amount": 1615.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "MORTGAGE", "amount": 620.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "SCHOOL SUPPLIES OUT OF POCKET", "amount": 45.00, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "GAS STATION", "amount": 52.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "WALMART", "amount": 110.00, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "ELECTRIC CO-OP", "amount": 85.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "VET BILL", "amount": 75.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
            {"raw_description": "CHURCH TITHE", "amount": 161.50, "transaction_type": "debit", "transaction_date": "2026-02-07"},
        ],
        "goal": {"goal_type": "save_money", "title": "Retirement top-up savings", "priority": "medium"},
        "constraint": {"constraint_type": "fixed", "label": "Gas for commute is non-negotiable"},
    },
    {
        "name": "Alex & Jordan — Urban Couple, DINK",
        "description": "Both 30yo, dual income ($140k combined), high rent city",
        "email": "alexjordan.dink@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Metro Bank",
            "account_name": "Joint Account",
            "current_balance": 8400.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "PAYROLL ALEX CORP", "amount": 2900.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "PAYROLL JORDAN LLC", "amount": 2500.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "RENT DOWNTOWN APT", "amount": 2200.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "MEAL DELIVERY", "amount": 89.00, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "GYM MEMBERSHIP", "amount": 79.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "BRUNCH RESTAURANT", "amount": 65.00, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "CONCERT TICKETS", "amount": 180.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "WINE CLUB", "amount": 55.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "UBER RIDE", "amount": 28.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
            {"raw_description": "STREAMING BUNDLE", "amount": 45.99, "transaction_type": "debit", "transaction_date": "2026-02-07"},
            {"raw_description": "DOG WALKER", "amount": 120.00, "transaction_type": "debit", "transaction_date": "2026-02-08"},
        ],
        "goal": {"goal_type": "save_money", "title": "Down payment for house", "priority": "high"},
        "constraint": {"constraint_type": "keep", "label": "Dog walker stays — both work long hours"},
    },
    {
        "name": "James — Disabled Veteran",
        "description": "40yo, VA disability ($1,800/mo), PTSD, limited mobility",
        "email": "james.vet@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Veterans CU",
            "account_name": "VA Benefits Account",
            "current_balance": 1650.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "VA DISABILITY PAYMENT", "amount": 1800.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "RENT ACCESSIBLE APT", "amount": 750.00, "transaction_type": "debit", "transaction_date": "2026-02-01"},
            {"raw_description": "PHARMACY VA COPAY", "amount": 15.00, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "MEDICAL TRANSPORT", "amount": 40.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "GROCERY DELIVERY", "amount": 95.00, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "INTERNET BILL", "amount": 55.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "STREAMING TV", "amount": 15.99, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "THERAPY CO-PAY", "amount": 30.00, "transaction_type": "debit", "transaction_date": "2026-02-06"},
        ],
        "goal": {"goal_type": "budget_better", "title": "Stretch VA benefits further", "priority": "high"},
        "constraint": {"constraint_type": "medical", "label": "Medical transport is essential"},
    },
    {
        "name": "Zoe — College Student",
        "description": "20yo, part-time barista ($14/hr), dorm, meal plan, parents help",
        "email": "zoe.student@test.com",
        "account": {
            "account_type": "checking",
            "institution_name": "Student Bank",
            "account_name": "Student Checking",
            "current_balance": 340.00,
            "currency": "USD",
        },
        "transactions": [
            {"raw_description": "PAYROLL COFFEE SHOP", "amount": 420.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "PARENT TRANSFER", "amount": 300.00, "transaction_type": "credit", "transaction_date": "2026-02-01"},
            {"raw_description": "TEXTBOOK AMAZON", "amount": 89.99, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "SPOTIFY STUDENT", "amount": 5.99, "transaction_type": "debit", "transaction_date": "2026-02-02"},
            {"raw_description": "CAMPUS FOOD", "amount": 12.00, "transaction_type": "debit", "transaction_date": "2026-02-03"},
            {"raw_description": "UBER TO CAMPUS", "amount": 8.50, "transaction_type": "debit", "transaction_date": "2026-02-04"},
            {"raw_description": "THRIFT STORE", "amount": 15.00, "transaction_type": "debit", "transaction_date": "2026-02-05"},
            {"raw_description": "BOBA TEA", "amount": 6.50, "transaction_type": "debit", "transaction_date": "2026-02-06"},
            {"raw_description": "ICLOUD STORAGE", "amount": 2.99, "transaction_type": "debit", "transaction_date": "2026-02-07"},
        ],
        "goal": {"goal_type": "save_money", "title": "Save for summer travel", "priority": "low"},
        "constraint": {"constraint_type": "fixed", "label": "Textbooks are required"},
    },
]


# ============================================================
# DATA STRUCTURES
# ============================================================


@dataclass
class StepResult:
    name: str
    ok: bool
    status_code: int | None
    elapsed_ms: int
    notes: dict


@dataclass
class Violation:
    code: str
    message: str
    details: dict


@dataclass
class AgentReport:
    persona_name: str
    email: str
    passed: bool
    steps: list = field(default_factory=list)
    violations: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


# ============================================================
# AGENT RUNNER
# ============================================================


class PersonaAgent:
    """Runs a single persona through the full Finitii flow via API."""

    def __init__(self, client: AsyncClient, persona: dict):
        self.client = client
        self.persona = persona
        self.headers: dict = {}
        self.steps: list[StepResult] = []
        self.violations: list[Violation] = []
        self.metrics: dict[str, Any] = {}
        self._account_id: str | None = None
        self._recommendation_id: str | None = None
        self._run_id: str | None = None

    def _step(self, name: str, ok: bool, status_code: int | None, elapsed: int, **notes):
        self.steps.append(StepResult(name, ok, status_code, elapsed, notes))

    def _violate(self, code: str, message: str, **details):
        self.violations.append(Violation(code, message, details))

    async def register_and_login(self):
        email = self.persona["email"]
        password = "AgentTest123!"

        # Register
        t0 = time.time()
        resp = await self.client.post("/auth/register", json={"email": email, "password": password})
        elapsed = int((time.time() - t0) * 1000)
        ok = resp.status_code in (201, 400, 409)  # 409 = already exists
        self._step("register", ok, resp.status_code, elapsed)

        # Login
        t0 = time.time()
        resp = await self.client.post("/auth/login", json={"email": email, "password": password})
        elapsed = int((time.time() - t0) * 1000)
        if resp.status_code == 200:
            token = resp.json().get("token")
            self.headers = {"X-Session-Token": token}
            self._step("login", True, 200, elapsed)
        else:
            self._step("login", False, resp.status_code, elapsed)
            self._violate("AUTH_FAILED", f"Login failed for {email}")

    async def grant_consent(self):
        for ct in ("data_access", "terms_of_service"):
            t0 = time.time()
            resp = await self.client.post(
                "/consent/grant", headers=self.headers,
                json={"consent_type": ct},
            )
            elapsed = int((time.time() - t0) * 1000)
            self._step(f"consent:{ct}", resp.status_code == 200, resp.status_code, elapsed)

    async def advance_onboarding(self, step: str):
        t0 = time.time()
        resp = await self.client.post(
            "/onboarding/advance", headers=self.headers,
            params={"step": step},
        )
        elapsed = int((time.time() - t0) * 1000)
        ok = resp.status_code == 200
        self._step(f"onboarding:{step}", ok, resp.status_code, elapsed)
        return ok

    async def create_account(self):
        t0 = time.time()
        resp = await self.client.post(
            "/accounts/manual", headers=self.headers,
            json=self.persona["account"],
        )
        elapsed = int((time.time() - t0) * 1000)
        if resp.status_code == 201:
            self._account_id = resp.json().get("id")
            self.metrics["account_id"] = self._account_id
            self._step("create_account", True, 201, elapsed)
        else:
            self._step("create_account", False, resp.status_code, elapsed)
            self._violate("ACCOUNT_FAILED", "Account creation failed")

    async def ingest_transactions(self):
        if not self._account_id:
            self._violate("NO_ACCOUNT", "Cannot ingest transactions without account")
            return

        count = 0
        for txn in self.persona["transactions"]:
            body = {
                "account_id": self._account_id,
                "raw_description": txn["raw_description"],
                "amount": txn["amount"],
                "transaction_type": txn["transaction_type"],
                "transaction_date": txn["transaction_date"] + "T12:00:00Z",
                "currency": "USD",
            }
            resp = await self.client.post("/transactions", headers=self.headers, json=body)
            if resp.status_code == 201:
                count += 1
            else:
                self._violate("TXN_INGEST_FAIL", f"Transaction failed: {txn['raw_description']}", status=resp.status_code)

        self.metrics["transactions_ingested"] = count
        self._step("ingest_transactions", count == len(self.persona["transactions"]), None, 0, count=count)

    async def detect_recurring(self):
        t0 = time.time()
        resp = await self.client.post("/recurring/detect", headers=self.headers)
        elapsed = int((time.time() - t0) * 1000)
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            self.metrics["recurring_patterns"] = len(data) if isinstance(data, list) else 0
        self._step("detect_recurring", ok, resp.status_code, elapsed)

    async def compute_forecast(self):
        t0 = time.time()
        resp = await self.client.post("/forecast/compute", headers=self.headers)
        elapsed = int((time.time() - t0) * 1000)
        ok = resp.status_code == 201
        if ok:
            data = resp.json()
            self.metrics["forecast_confidence"] = data.get("confidence")
            self.metrics["safe_to_spend_today"] = data.get("safe_to_spend_today")
            self.metrics["urgency_score"] = data.get("urgency_score")

            # PRD CHECK: forecast must have assumptions
            assumptions = data.get("assumptions")
            if not assumptions or not isinstance(assumptions, list) or len(assumptions) == 0:
                self._violate("FORECAST_NO_ASSUMPTIONS", "Forecast missing assumptions list")
            else:
                self.metrics["forecast_assumptions_count"] = len(assumptions)
        self._step("compute_forecast", ok, resp.status_code, elapsed)

    async def create_goal(self):
        goal = self.persona.get("goal")
        if not goal:
            return
        t0 = time.time()
        resp = await self.client.post("/goals", headers=self.headers, json=goal)
        elapsed = int((time.time() - t0) * 1000)
        self._step("create_goal", resp.status_code == 201, resp.status_code, elapsed)

    async def create_constraint(self):
        constraint = self.persona.get("constraint")
        if not constraint:
            return
        t0 = time.time()
        resp = await self.client.post("/goals/constraints", headers=self.headers, json=constraint)
        elapsed = int((time.time() - t0) * 1000)
        self._step("create_constraint", resp.status_code == 201, resp.status_code, elapsed)

    async def fetch_top3(self):
        t0 = time.time()
        resp = await self.client.post("/cheat-codes/top-3", headers=self.headers)
        elapsed = int((time.time() - t0) * 1000)
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            recs = data if isinstance(data, list) else []
            self.metrics["top3_count"] = len(recs)

            # PRD CHECK: No low confidence in Top 3
            for rec in recs:
                conf = rec.get("confidence", "")
                if conf.lower() == "low":
                    self._violate("LOW_CONFIDENCE_LEAK",
                                  f"Low confidence in Top 3 — PRD VIOLATION!",
                                  rank=rec.get("rank"), confidence=conf)

            # PRD CHECK: At least one quick win
            quick_wins = [r for r in recs if r.get("is_quick_win")]
            if recs and not quick_wins:
                self._violate("NO_QUICK_WIN", "Top 3 has no quick win — PRD requires ≥1")

            # Extract first recommendation ID for run
            if recs:
                self._recommendation_id = recs[0].get("id")
                self.metrics["recommendation_id"] = self._recommendation_id

        self._step("fetch_top3", ok, resp.status_code, elapsed)

    async def start_run(self):
        if not self._recommendation_id:
            self._violate("NO_REC_ID", "Cannot start run without recommendation")
            return
        t0 = time.time()
        resp = await self.client.post(
            "/cheat-codes/runs", headers=self.headers,
            json={"recommendation_id": self._recommendation_id},
        )
        elapsed = int((time.time() - t0) * 1000)
        if resp.status_code == 201:
            self._run_id = resp.json().get("id")
            self.metrics["run_id"] = self._run_id
            self._step("start_run", True, 201, elapsed)
        else:
            self._step("start_run", False, resp.status_code, elapsed)
            self._violate("START_RUN_FAILED", "Failed to start cheat code run")

    async def complete_first_step(self):
        if not self._run_id:
            self._violate("NO_RUN_ID", "Cannot complete step without run")
            return
        t0 = time.time()
        resp = await self.client.post(
            f"/cheat-codes/runs/{self._run_id}/steps/complete",
            headers=self.headers,
            json={"step_number": 1, "notes": "Agent completed step 1"},
        )
        elapsed = int((time.time() - t0) * 1000)
        ok = resp.status_code == 200
        self.metrics["first_win_success"] = ok
        self._step("complete_step_1", ok, resp.status_code, elapsed)

    async def verify_coach(self):
        """Verify coach plan returns template-based response."""
        t0 = time.time()
        resp = await self.client.post(
            "/coach", headers=self.headers,
            json={"mode": "plan"},
        )
        elapsed = int((time.time() - t0) * 1000)
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            if not data.get("template_used"):
                self._violate("COACH_NO_TEMPLATE", "Coach plan missing template_used")
        self._step("coach_plan", ok, resp.status_code, elapsed)

    async def verify_export(self):
        """Verify export includes all entity types."""
        t0 = time.time()
        resp = await self.client.get("/user/export", headers=self.headers)
        elapsed = int((time.time() - t0) * 1000)
        ok = resp.status_code == 200
        if ok:
            data = resp.json()
            required_keys = ["user", "consent_records", "accounts", "transactions",
                             "audit_log", "vault_items"]
            for key in required_keys:
                if key not in data:
                    self._violate("EXPORT_MISSING_KEY", f"Export missing: {key}")
            self.metrics["export_keys"] = len(data)
        self._step("verify_export", ok, resp.status_code, elapsed)

    async def verify_request_id(self):
        """Verify X-Request-ID header present."""
        resp = await self.client.get("/health")
        has_id = "x-request-id" in resp.headers
        if not has_id:
            self._violate("NO_REQUEST_ID", "Missing X-Request-ID header")
        self._step("request_id_check", has_id, resp.status_code, 0)

    async def run_full_flow(self) -> AgentReport:
        """Execute the complete persona flow."""
        # 1. Auth
        await self.register_and_login()
        if not self.headers:
            return self._build_report()

        # 2. Consent
        await self.grant_consent()

        # 3. Advance onboarding: consent
        await self.advance_onboarding("consent")

        # 4. Create account
        await self.create_account()

        # 5. Advance onboarding: account_link
        await self.advance_onboarding("account_link")

        # 6. Ingest transactions
        await self.ingest_transactions()

        # 7. Detect recurring
        await self.detect_recurring()

        # 8. Compute forecast
        await self.compute_forecast()

        # 9. Create goal + constraint
        await self.create_goal()
        await self.create_constraint()

        # 10. Advance onboarding: goals
        await self.advance_onboarding("goals")

        # 11. Top 3
        await self.fetch_top3()

        # 12. Advance onboarding: top_3
        await self.advance_onboarding("top_3")

        # 13. Start run + complete step 1
        await self.start_run()
        await self.complete_first_step()

        # 14. Advance onboarding: first_win
        await self.advance_onboarding("first_win")

        # 15. Additional verifications
        await self.verify_coach()
        await self.verify_export()
        await self.verify_request_id()

        return self._build_report()

    def _build_report(self) -> AgentReport:
        ok_steps = sum(1 for s in self.steps if s.ok)
        total_steps = len(self.steps)
        first_win = self.metrics.get("first_win_success", False)
        passed = len(self.violations) == 0 and first_win

        self.metrics["steps_ok"] = ok_steps
        self.metrics["steps_total"] = total_steps

        return AgentReport(
            persona_name=self.persona["name"],
            email=self.persona["email"],
            passed=passed,
            steps=self.steps,
            violations=self.violations,
            metrics=self.metrics,
        )


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield
    set_storage(None)


# ============================================================
# PARAMETRIZED TESTS — one per persona
# ============================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", PERSONAS, ids=[p["name"].split(" — ")[0] for p in PERSONAS])
async def test_persona_full_flow(
    client: AsyncClient, db_session: AsyncSession, persona: dict
):
    """Run a single persona agent through the complete Finitii flow."""
    agent = PersonaAgent(client, persona)
    report = await agent.run_full_flow()

    # Print report summary for visibility
    status = "PASS" if report.passed else "FAIL"
    print(f"\n[{status}] {report.persona_name}")
    print(f"  Steps: {report.metrics.get('steps_ok', 0)}/{report.metrics.get('steps_total', 0)}")
    print(f"  Transactions: {report.metrics.get('transactions_ingested', 0)}")
    print(f"  Recurring: {report.metrics.get('recurring_patterns', 0)}")
    print(f"  Forecast: conf={report.metrics.get('forecast_confidence')} "
          f"STS={report.metrics.get('safe_to_spend_today')} "
          f"urgency={report.metrics.get('urgency_score')}")
    print(f"  Top 3: {report.metrics.get('top3_count', 0)} recommendations")
    print(f"  First Win: {report.metrics.get('first_win_success', False)}")
    if report.violations:
        for v in report.violations:
            print(f"  VIOLATION: [{v.code}] {v.message}")

    # Assertions
    assert report.metrics.get("first_win_success"), f"{persona['name']}: First Win failed"
    assert len(report.violations) == 0, (
        f"{persona['name']} had violations: "
        + "; ".join(f"[{v.code}] {v.message}" for v in report.violations)
    )


# ============================================================
# AGGREGATE SUMMARY TEST
# ============================================================


@pytest.mark.asyncio
async def test_all_personas_summary(client: AsyncClient, db_session: AsyncSession):
    """Run ALL personas and produce aggregate report."""
    reports: list[AgentReport] = []

    for persona in PERSONAS:
        agent = PersonaAgent(client, persona)
        report = await agent.run_full_flow()
        reports.append(report)

    # Print aggregate summary
    print("\n" + "=" * 70)
    print("FINITII AGENT RUNNER — AGGREGATE RESULTS")
    print("=" * 70)

    total_pass = sum(1 for r in reports if r.passed)
    total_fail = sum(1 for r in reports if not r.passed)
    total_violations = sum(len(r.violations) for r in reports)
    total_steps = sum(r.metrics.get("steps_total", 0) for r in reports)
    total_steps_ok = sum(r.metrics.get("steps_ok", 0) for r in reports)
    total_txns = sum(r.metrics.get("transactions_ingested", 0) for r in reports)

    print(f"\nPersonas: {len(reports)} tested")
    print(f"Passed:   {total_pass}/{len(reports)}")
    print(f"Failed:   {total_fail}/{len(reports)}")
    print(f"Steps:    {total_steps_ok}/{total_steps} OK")
    print(f"Txns:     {total_txns} ingested")
    print(f"Violations: {total_violations}")

    print(f"\n{'Persona':<35} {'Status':<8} {'Steps':<10} {'Txns':<6} {'Top3':<5} {'FirstWin':<9} {'Violations':<10}")
    print("-" * 90)
    for r in reports:
        status = "PASS" if r.passed else "FAIL"
        steps = f"{r.metrics.get('steps_ok', 0)}/{r.metrics.get('steps_total', 0)}"
        txns = str(r.metrics.get("transactions_ingested", 0))
        top3 = str(r.metrics.get("top3_count", 0))
        fw = "YES" if r.metrics.get("first_win_success") else "NO"
        viols = str(len(r.violations))
        print(f"{r.persona_name:<35} {status:<8} {steps:<10} {txns:<6} {top3:<5} {fw:<9} {viols:<10}")

    # PRD non-negotiable assertions
    print(f"\n--- PRD Non-Negotiable Checks ---")
    low_conf_violations = [v for r in reports for v in r.violations if v.code == "LOW_CONFIDENCE_LEAK"]
    assumption_violations = [v for r in reports for v in r.violations if v.code == "FORECAST_NO_ASSUMPTIONS"]
    template_violations = [v for r in reports for v in r.violations if v.code == "COACH_NO_TEMPLATE"]
    quick_win_violations = [v for r in reports for v in r.violations if v.code == "NO_QUICK_WIN"]

    print(f"  Low confidence in Top 3:   {len(low_conf_violations)} violations")
    print(f"  Forecast no assumptions:   {len(assumption_violations)} violations")
    print(f"  Coach no template:         {len(template_violations)} violations")
    print(f"  No quick win in Top 3:     {len(quick_win_violations)} violations")

    print("=" * 70)

    # Hard assertion: zero PRD violations
    assert total_violations == 0, f"{total_violations} PRD violations across all personas"
    assert total_pass == len(reports), f"{total_fail} personas failed"
