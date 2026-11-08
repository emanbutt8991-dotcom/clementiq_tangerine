"""Financial shock simulator.

Two modes:
  * judging  — only the transformations stated in the Tangerine README:
               income_after = multiplier × I,  spending_after = S + pct × H (+ $ amounts),
               one-off costs subtract from B. No caps, no behavioural assumptions.
  * extended — adds explicitly labelled assumptions: the EI weekly maximum, income returning to
               0 once EI ends, estimated category allocations for transport/groceries, and a
               month-by-month balance projection.

Shocks are composable. Identical validated inputs always produce identical outputs.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .allocation import ESTIMATED_ALLOCATION, ALLOCATION_SOURCE
from .metrics import Baseline
from .provenance import envelope
from .runway import compute_runway

ShockType = Literal[
    "job_loss", "income_reduction", "reduced_hours", "rent_increase", "bill_inflation",
    "emergency_expense", "vehicle_repair", "transport_cost", "grocery_cost",
    "loan_payment_increase", "spending_inflation",
]

SHOCK_LABELS: dict[str, str] = {
    "job_loss": "Job loss",
    "income_reduction": "Partial loss of income",
    "reduced_hours": "Reduced working hours",
    "rent_increase": "Rent increase",
    "bill_inflation": "Household bill inflation",
    "emergency_expense": "Medical / emergency expense",
    "vehicle_repair": "Vehicle repair",
    "transport_cost": "Higher transportation costs",
    "grocery_cost": "Higher grocery costs",
    "loan_payment_increase": "Loan payment increase",
    "spending_inflation": "General price inflation",
}


class ShockComponent(BaseModel):
    type: ShockType
    # Income shocks
    income_replacement_pct: float | None = Field(None, ge=0, le=100,
        description="job_loss: % of usual income still received (EI = 55)")
    pct: float | None = Field(None, ge=0, le=500, description="percentage size of the shock")
    amount: float | None = Field(None, ge=0, le=10_000_000, description="CAD amount")
    months_of_spending: float | None = Field(None, ge=0, le=36,
        description="one-off cost expressed as multiples of typical monthly spending S")
    duration_months: int | None = Field(None, ge=1, le=120)
    wage_share_pct: float = Field(100, ge=0, le=100,
        description="reduced_hours: share of money_in that is wages (judging mode forces 100)")

    @model_validator(mode="after")
    def _check(self) -> "ShockComponent":
        t = self.type
        if t == "job_loss" and self.income_replacement_pct is None:
            self.income_replacement_pct = 0.0
        if t in ("income_reduction", "reduced_hours", "bill_inflation", "spending_inflation") and self.pct is None:
            raise ValueError(f"{t} requires pct")
        if t in ("rent_increase", "loan_payment_increase", "transport_cost", "grocery_cost") and \
                self.pct is None and self.amount is None:
            raise ValueError(f"{t} requires pct or amount")
        if t in ("emergency_expense", "vehicle_repair") and self.amount is None and self.months_of_spending is None:
            raise ValueError(f"{t} requires amount or months_of_spending")
        return self


class ShockRequest(BaseModel):
    account_id: int
    components: list[ShockComponent] = Field(min_length=1, max_length=12)
    mode: Literal["judging", "extended"] = "judging"
    horizon_months: int = Field(24, ge=3, le=120)
    discretionary_cut_pct: float = Field(0, ge=0, le=100,
        description="optional behavioural response (extended mode only)")


def _ei_monthly_cap(weekly_max: float) -> float:
    return weekly_max * 52.0 / 12.0


def apply_shocks(b: Baseline, req: ShockRequest, ei_weekly_max: float = 695.0) -> dict[str, Any]:
    judging = req.mode == "judging"
    income_mult = 1.0
    income_floor_after_duration: float | None = None
    income_duration: int | None = None
    spend_add = 0.0
    one_off = 0.0
    assumptions: list[str] = []
    warnings: list[str] = []
    effects: list[dict[str, Any]] = []

    for c in req.components:
        d_income = 0.0
        d_spend = 0.0
        d_once = 0.0
        note = ""
        if c.type == "job_loss":
            rep = (c.income_replacement_pct or 0) / 100.0
            new_income = rep * b.I
            if not judging and rep > 0:
                cap = _ei_monthly_cap(ei_weekly_max)
                if new_income > cap:
                    assumptions.append(
                        f"EI capped at ${ei_weekly_max:,.0f}/week (≈${cap:,.0f}/month) — canada.ca maximum.")
                    new_income = cap
            mult = (new_income / b.I) if b.I > 0 else 0.0
            d_income = new_income - b.I * income_mult
            income_mult *= mult
            income_duration = c.duration_months
            if c.duration_months:
                income_floor_after_duration = 0.0
                note = f"income at {c.income_replacement_pct:g}% for {c.duration_months} months"
            else:
                note = f"income at {c.income_replacement_pct:g}% of usual"
        elif c.type in ("income_reduction", "reduced_hours"):
            share = 1.0 if (judging or c.type == "income_reduction") else c.wage_share_pct / 100.0
            if c.type == "reduced_hours" and not judging and share < 1:
                assumptions.append(f"{c.wage_share_pct:g}% of money_in assumed to be wages affected by hours.")
            mult = 1.0 - (c.pct or 0) / 100.0 * share
            d_income = b.I * income_mult * (mult - 1.0)
            income_mult *= mult
            if c.duration_months:
                income_duration = c.duration_months
            note = f"income −{c.pct:g}%"
        elif c.type in ("rent_increase", "bill_inflation"):
            if c.pct is not None:
                d_spend = (c.pct / 100.0) * b.H
                note = f"spending + {c.pct:g}% × H"
            else:
                d_spend = float(c.amount or 0)
                note = f"spending + ${d_spend:,.2f}/month"
            if c.type == "rent_increase" and b.H == 0:
                warnings.append("This account has no labelled household bills (H = 0); "
                                "a percentage rent shock has no effect — use a $ amount.")
        elif c.type == "spending_inflation":
            d_spend = (c.pct or 0) / 100.0 * b.S
            note = f"spending + {c.pct:g}% × S"
        elif c.type == "loan_payment_increase":
            if c.pct is not None:
                d_spend = (c.pct / 100.0) * b.P
                note = f"spending + {c.pct:g}% × P"
                if b.P == 0:
                    warnings.append("No running loan (P = 0); percentage loan shock has no effect.")
            else:
                d_spend = float(c.amount or 0)
                note = f"spending + ${d_spend:,.2f}/month"
        elif c.type in ("transport_cost", "grocery_cost"):
            cat = "transportation" if c.type == "transport_cost" else "food"
            if c.amount is not None:
                d_spend = float(c.amount)
                note = f"spending + ${d_spend:,.2f}/month"
            else:
                if judging:
                    raise ValueError(f"{c.type} with pct requires extended mode (estimated allocation); "
                                     "use an amount in judging mode")
                share = ESTIMATED_ALLOCATION[cat]
                base = share * b.D
                d_spend = (c.pct or 0) / 100.0 * base
                assumptions.append(
                    f"ESTIMATE: {cat} ≈ {share:.0%} of discretionary outflows D "
                    f"(${base:,.2f}/month) — {ALLOCATION_SOURCE}. Not actual transaction history.")
                note = f"spending + {c.pct:g}% × estimated {cat} spending"
        elif c.type in ("emergency_expense", "vehicle_repair"):
            if c.months_of_spending is not None:
                d_once = c.months_of_spending * b.S
                note = f"one-off = {c.months_of_spending:g} × S"
            else:
                d_once = float(c.amount or 0)
                note = f"one-off ${d_once:,.2f}"
        spend_add += d_spend
        one_off += d_once
        effects.append({
            "type": c.type, "label": SHOCK_LABELS[c.type], "delta_income": d_income,
            "delta_spending": d_spend, "one_off": d_once, "rule": note,
            "params": c.model_dump(exclude_none=True),
        })

    income_after = b.I * income_mult
    spending_after = b.S + spend_add
    base_rw = compute_runway(b.B, b.I, b.S, 0.0)
    shock_rw = compute_runway(b.B, income_after, spending_after, one_off)

    cut_info = None
    if not judging and req.discretionary_cut_pct > 0:
        cut = req.discretionary_cut_pct / 100.0 * b.D
        assumptions.append(f"Behavioural response: discretionary outflows cut by "
                           f"{req.discretionary_cut_pct:g}% (−${cut:,.2f}/month).")
        spending_after_cut = spending_after - cut
        cut_rw = compute_runway(b.B, income_after, spending_after_cut, one_off)
        cut_info = {"cut_amount": cut, "spending_after": spending_after_cut, "runway": cut_rw.to_dict()}
        spending_for_projection = spending_after_cut
    else:
        spending_for_projection = spending_after

    # Month-by-month projection (illustrative; the authoritative judging number is shock_rw).
    projection = []
    bal_base = b.B
    bal_shock = b.B - one_off
    depletion_month = None
    for m in range(1, req.horizon_months + 1):
        inc = income_after
        if income_duration and m > income_duration:
            if income_floor_after_duration is not None and not judging:
                inc = income_floor_after_duration  # EI exhausted, no assumed re-employment
            elif income_floor_after_duration is not None and judging:
                inc = income_after  # judging formula is steady-state; keep shock income
            else:
                inc = b.I
        bal_base += b.I - b.S
        bal_shock += inc - spending_for_projection
        if depletion_month is None and bal_shock <= 0:
            depletion_month = m
        projection.append({"month": m, "baseline_balance": bal_base, "scenario_balance": bal_shock,
                           "scenario_income": inc, "scenario_spending": spending_for_projection})
    if not judging and income_floor_after_duration is not None:
        assumptions.append("After the benefit period ends, income is modeled as $0 (no re-employment assumed).")

    verdict = None
    durations = [c.duration_months for c in req.components if c.duration_months]
    if durations:
        need = max(durations)
        ok = shock_rw.no_shortfall or shock_rw.months >= need
        verdict = {
            "required_months": need, "survives": ok,
            "text": (f"Yes — runway {shock_rw.display} months covers the {need}-month shock."
                     if ok else f"No — runway {shock_rw.display} months is short of the {need}-month shock "
                                f"by {need - shock_rw.months:.1f} months."),
            "shortfall_over_period": max(0.0, shock_rw.gap * need - shock_rw.buffer_left) if not ok else 0.0,
        }

    if judging:
        assumptions.insert(0, "Judging Mode: Tangerine README formulas only, no additional assumptions.")

    payload = {
        "account_id": b.account_id,
        "mode": req.mode,
        "baseline": {**b.judging_dict(), "income": b.I, "spending": b.S, "gap": b.S - b.I,
                     "runway": base_rw.to_dict()},
        "scenario": {"income": income_after, "spending": spending_after, "one_off_costs": one_off,
                     "buffer_left": b.B - one_off, "gap": spending_after - income_after,
                     "runway": shock_rw.to_dict()},
        "deltas": {
            "income": income_after - b.I,
            "spending": spending_after - b.S,
            "monthly_shortfall_change": (spending_after - income_after) - (b.S - b.I),
            "buffer_change": -one_off,
            "runway_change": shock_rw.months - base_rw.months,
        },
        "effects": effects,
        "verdict": verdict,
        "behavioural_cut": cut_info,
        "projection": projection,
        "depletion_month": depletion_month,
        "assumptions": assumptions,
        "warnings": warnings + b.warnings,
        "formula": {
            "income_after": "I × Π(income multipliers)",
            "spending_after": "S + Σ(pct × H | pct × S | $ amounts)",
            "runway": "min((B − one_off) / (spending_after − income_after), 120)",
        },
    }
    return envelope(payload, {"baseline": b.judging_dict(), "request": req.model_dump()})


# Official twist-card presets from the README plus common extras.
PRESETS: list[dict[str, Any]] = [
    {"id": "ei55_6m", "name": "Laid off — EI 55% for 6 months", "judging": True,
     "components": [{"type": "job_loss", "income_replacement_pct": 55, "duration_months": 6}]},
    {"id": "furnace", "name": "Furnace dies — repair = 1 month of spending", "judging": True,
     "components": [{"type": "emergency_expense", "months_of_spending": 1}]},
    {"id": "ei55_bills15", "name": "Job loss (EI 55%) + household bills +15%", "judging": True,
     "components": [{"type": "job_loss", "income_replacement_pct": 55},
                    {"type": "bill_inflation", "pct": 15}]},
    {"id": "job_loss_total", "name": "Job loss with no income", "judging": True,
     "components": [{"type": "job_loss", "income_replacement_pct": 0}]},
    {"id": "rent10", "name": "Rent / household bills +10%", "judging": True,
     "components": [{"type": "rent_increase", "pct": 10}]},
    {"id": "hours20", "name": "Hours cut 20%", "judging": True,
     "components": [{"type": "reduced_hours", "pct": 20}]},
    {"id": "car2500", "name": "Car repair $2,500", "judging": True,
     "components": [{"type": "vehicle_repair", "amount": 2500}]},
    {"id": "perfect_storm", "name": "Perfect storm (EI 55%, bills +15%, $3,000 emergency)", "judging": True,
     "components": [{"type": "job_loss", "income_replacement_pct": 55, "duration_months": 6},
                    {"type": "bill_inflation", "pct": 15},
                    {"type": "emergency_expense", "amount": 3000}]},
    {"id": "mortgage_renewal", "name": "Mortgage renewal — loan payment +6%", "judging": True,
     "components": [{"type": "loan_payment_increase", "pct": 6}]},
    {"id": "cost_of_living", "name": "Cost of living squeeze (extended: groceries +8%, transport +12%)",
     "judging": False,
     "components": [{"type": "grocery_cost", "pct": 8}, {"type": "transport_cost", "pct": 12}]},
]
