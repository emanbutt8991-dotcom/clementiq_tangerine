"""Portfolio "needs attention" list: accounts with a risk flag TODAY, using the same rules as the
per-account /obligations check and the Stress Test page.

Flags (any one puts an account on the list):
  short   — this month's fixed payments (standing orders + a running loan with no loan standing order)
            exceed the latest month-end balance
  behind  — loan status D (running, client in arrears)
  thin    — buffer B below one month of typical spending S (S > 0)

Active accounts only: S > 0 and data within the last 6 months of the dataset. Flags are for outreach and
help, never for credit decisions; the API and UI say so.
"""
from __future__ import annotations

import pandas as pd

SEVERITY = {"short": 0, "behind": 1, "thin": 2}


def compute_attention(baselines: pd.DataFrame, monthly: pd.DataFrame, orders: pd.DataFrame,
                      loans: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Return (flagged accounts sorted by severity then gap, number of active accounts)."""
    if baselines.empty:
        return pd.DataFrame(), 0
    b = baselines.set_index("account_id")
    last = (monthly.sort_values(["account_id", "month"]).groupby("account_id")
            .agg(balance=("month_end_balance", "last")))
    b = b.join(last)

    o = orders.copy()
    o["purpose_l"] = o["purpose"].fillna("").str.strip().str.lower()
    so_total = o.groupby("account_id")["amount"].sum().rename("so_total")
    has_lp = o[o.purpose_l == "loan payment"].groupby("account_id").size().rename("has_lp")
    ln = loans.drop_duplicates("account_id").set_index("account_id")[["status", "monthly_payment"]]
    b = b.join(so_total).join(has_lp).join(ln)
    b["so_total"] = b["so_total"].fillna(0.0)
    running = b["status"].isin(["C", "D"])
    b["fixed_total"] = b["so_total"] + b["monthly_payment"].where(running & b["has_lp"].isna(), 0.0).fillna(0.0)
    b["left_after_fixed"] = b["balance"] - b["fixed_total"]

    # Active: some spending, and data within six months of the newest month in the dataset.
    newest = pd.Period(b["last_month"].max(), freq="M")
    recent = b["last_month"].map(lambda m: (newest - pd.Period(m, freq="M")).n <= 5)
    active = b[(b["spending_S"] > 0) & recent].copy()

    active["short"] = active["left_after_fixed"] < 0
    active["behind"] = active["status"].eq("D")
    active["thin"] = active["buffer_B"] < active["spending_S"]
    flagged = active[active["short"] | active["behind"] | active["thin"]].copy()
    flagged["flags"] = flagged.apply(lambda r: [k for k in ("short", "behind", "thin") if r[k]], axis=1)
    flagged["severity"] = flagged["flags"].map(lambda f: min(SEVERITY[k] for k in f))
    flagged = flagged.sort_values(["severity", "left_after_fixed"], kind="mergesort")
    return flagged.reset_index(), int(len(active))
