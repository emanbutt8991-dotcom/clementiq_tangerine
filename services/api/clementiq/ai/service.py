"""High-level explanation services. Gemini when available; deterministic templates otherwise.

Each result reports which engine produced it, so the UI can label it, and whether every dollar
figure in the AI text was verified against Clement Core output.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core.provenance import stable_hash
from . import gemini
from .sanitize import clean_untrusted, wrap_sources
from .schemas import AlertExplanation, NewsSummary, PlanExplanation, ScenarioExplanation

log = logging.getLogger("clementiq.ai")
FALLBACK_ENGINE = "clement-core-template"


def _money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:,.0f}"


def _cached(db: Session | None, kind: str, h: str) -> dict[str, Any] | None:
    if db is None:
        return None
    row = db.execute(select(models.AIExplanation).where(models.AIExplanation.kind == kind,
                                                        models.AIExplanation.input_hash == h)
                     .order_by(models.AIExplanation.id.desc())).scalars().first()
    return row.output if row else None


def _store(db: Session | None, kind: str, h: str, out: dict[str, Any]) -> None:
    if db is None:
        return
    db.add(models.AIExplanation(kind=kind, input_hash=h, engine=out["engine"], model=out.get("model"), output=out))
    db.commit()


AI_OFF_REASON = "Personalized AI guidance is turned off in Settings → Privacy & AI"


def _run(db, kind: str, facts: dict[str, Any], prompt: str, schema, fallback_fn, use_cache=True,
         allow_ai: bool = True) -> dict[str, Any]:
    if not allow_ai:
        return {"engine": FALLBACK_ENGINE, "content": fallback_fn(), "fallback_reason": AI_OFF_REASON}
    h = stable_hash({"kind": kind, "facts": facts})
    if use_cache and (hit := _cached(db, kind, h)):
        return {**hit, "cached": True}
    allowed = gemini.collect_numbers(facts)
    try:
        parsed, meta = gemini.generate_json(prompt, schema)
        content = parsed.model_dump()
        check = gemini.verify_numbers(json.dumps(content), allowed)
        if not check["ok"]:
            log.warning("Gemini %s output had unverified numbers %s; using template", kind, check["unverified"])
            out = {"engine": FALLBACK_ENGINE, "content": fallback_fn(), "number_check": check,
                   "fallback_reason": "AI output contained figures not produced by Clement Core"}
        else:
            out = {"engine": meta["engine"], "model": meta["model"], "content": content, "number_check": check}
    except gemini.GeminiUnavailable as exc:
        out = {"engine": FALLBACK_ENGINE, "content": fallback_fn(), "fallback_reason": str(exc)[:200]}
    _store(db, kind, h, out)
    return out


# ------------------------------------------------------------------ scenario ----------
def explain_scenario(db: Session | None, sim: dict[str, Any], context: dict[str, Any],
                     sources: list[dict[str, Any]] | None = None, allow_ai: bool = True) -> dict[str, Any]:
    facts = {
        "customer": context,
        "baseline": {k: sim["baseline"][k] for k in ("income", "spending", "B", "H", "F", "P")},
        "baseline_runway": sim["baseline"]["runway"]["display"],
        "scenario": {k: sim["scenario"][k] for k in ("income", "spending", "one_off_costs", "buffer_left", "gap")},
        "scenario_runway": sim["scenario"]["runway"]["display"],
        "effects": [{"label": e["label"], "rule": e["rule"], "delta_income": e["delta_income"],
                     "delta_spending": e["delta_spending"], "one_off": e["one_off"]} for e in sim["effects"]],
        "deltas": sim.get("deltas"),
        "verdict": sim.get("verdict"),
        "assumptions": sim.get("assumptions", []),
    }
    src_text, flagged = wrap_sources(sources or [])
    prompt = (
        "Explain this Clement Core shock simulation to the customer.\n"
        f"CLEMENT CORE RESULT (authoritative):\n{json.dumps(facts, default=str)}\n\n"
        + (f"SOURCES:\n{src_text}\n\n" if sources else "No news sources supplied; do not refer to any.\n")
        + "Fill every field. options: 2-4 concrete, non-guaranteed preparation options grounded in the numbers.")

    def fb() -> dict[str, Any]:
        sc, base = sim["scenario"], sim["baseline"]
        v = sim.get("verdict")
        labels = ", ".join(e["label"] for e in sim["effects"])
        gap = sc["gap"]
        return {
            "headline": (v["text"] if v else f"Runway moves from {base['runway']['display']} to "
                         f"{sc['runway']['display']} months"),
            "what_happened": f"Scenario applied: {labels}.",
            "why_it_matters": "Runway is how many months the savings buffer covers the monthly gap between "
                              "spending and income.",
            "affected_categories": [e["label"] for e in sim["effects"]],
            "what_the_numbers_show": (
                f"Income goes from {_money(base['income'])} to {_money(sc['income'])} a month and spending from "
                f"{_money(base['spending'])} to {_money(sc['spending'])}. "
                + (f"One-off costs of {_money(sc['one_off_costs'])} reduce the buffer to {_money(sc['buffer_left'])}. "
                   if sc["one_off_costs"] else "")
                + (f"The monthly shortfall is {_money(gap)}, giving {sc['runway']['display']} months of runway."
                   if gap > 0 else "Income still covers spending, so there is no monthly shortfall.")),
            "options": [
                {"action": "Review the Backup Plan tiers", "rationale": "They show how trimming discretionary "
                 "outflows changes runway under this exact shock."},
                {"action": "Build the buffer with the Goal Plan", "rationale": "A larger buffer is the most direct "
                 "way to extend runway."},
            ],
            "confidence": "high",
            "uncertainty": "Uses typical (median) months; real months vary. " + " ".join(sim.get("assumptions", [])[:2]),
            "source_ids": [],
        }

    out = _run(db, "scenario", {**facts, "sources": [s.get("id") for s in sources or []]}, prompt,
               ScenarioExplanation, fb, allow_ai=allow_ai)
    if flagged:
        out["injection_flags"] = flagged
    return out


def explain_plan(db: Session | None, plan: dict[str, Any], context: dict[str, Any], allow_ai: bool = True) -> dict[str, Any]:
    if plan["plan_type"] == "goal":
        facts = {k: plan[k] for k in ("current_buffer", "target", "gap", "monthly_surplus",
                                      "recommended_monthly_contribution", "months_to_goal", "status")}
    else:
        facts = {"monthly_shortfall": plan["monthly_shortfall"],
                 "runway_no_action": plan["alternatives"][0]["runway"]["display"],
                 "best_tier_runway": plan["best_tier"]["runway"]["display"],
                 "best_tier_cut_pct": plan["best_tier"]["discretionary_cut_pct"],
                 "cut_pct_to_close_gap": plan["discretionary_cut_pct_to_close_gap"],
                 "immediate_actions": [a["action"] for a in plan["immediate_actions"]]}
    facts["customer"] = context
    prompt = (f"Explain this Clement Core {plan['plan_type']} plan in plain language.\n"
              f"PLAN (authoritative):\n{json.dumps(facts, default=str)}\n"
              "key_steps: 3-5 short steps. caveats: note figures are modeled, not guaranteed.")

    def fb() -> dict[str, Any]:
        if plan["plan_type"] == "goal":
            if plan["status"] == "reached":
                s = f"The current buffer of {_money(plan['current_buffer'])} already meets the {_money(plan['target'])} target."
            elif plan["months_to_goal"] is None:
                s = (f"The target is {_money(plan['target'])}, {_money(plan['gap'])} above the current buffer. "
                     "Spending currently uses all income, so reductions are needed before saving can start.")
            else:
                s = (f"Setting aside {_money(plan['recommended_monthly_contribution'])} a month closes the "
                     f"{_money(plan['gap'])} gap to a {_money(plan['target'])} emergency fund in about "
                     f"{plan['months_to_goal']} months.")
            steps = ["Automate the monthly transfer on payday.", "Track progress against each milestone.",
                     "Revisit the target if income or bills change."]
        else:
            s = (f"Under this shock the monthly shortfall is {_money(plan['monthly_shortfall'])}. With no changes, runway is "
                 f"{plan['alternatives'][0]['runway']['display']} months; the best modeled option reaches "
                 f"{plan['best_tier']['runway']['display']} months.")
            steps = [a["action"] for a in plan["immediate_actions"][:4]]
        return {"summary": s, "key_steps": steps, "encouragement": "Small, steady steps add up.",
                "caveats": "Figures are modeled from typical months and are not guarantees."}

    return _run(db, f"plan_{plan['plan_type']}", facts, prompt, PlanExplanation, fb, allow_ai=allow_ai)


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def summarize_news(db: Session | None, item: dict[str, Any], cortex: dict[str, Any] | None = None) -> dict[str, Any]:
    """`cortex`: a grounded Snowflake Cortex analysis. When given, Gemini sees ONLY the title, the
    verified facts and the uncertainties, and may use no number that is not in those facts."""
    if cortex is not None:
        return _summarize_from_cortex(db, item, cortex)
    src_text, flagged = wrap_sources([item])
    prompt = ("Summarise this source neutrally for a household-finance audience in <= 45 words, using only "
              "what it states. Classify whether it reports a confirmed event, a forecast, an opinion or "
              "speculation. exposure_categories: household spending categories or asset classes that could "
              f"be affected (e.g. transportation, household_bills, food, loan_payments, savings, equities).\n\n{src_text}")

    def fb() -> dict[str, Any]:
        return {"summary": f"{item.get('source_name')} reports: {item.get('headline')}",
                "topic": item.get("topic", "other"), "classification": "unclear",
                "exposure_categories": item.get("exposure_categories", []),
                "household_relevance": "indirect",
                "confidence_note": "Headline-only summary; open the original source for details."}

    out = _run(db, "news", {"id": item.get("id"), "headline": item.get("headline"), "url": item.get("url")},
               prompt, NewsSummary, fb)
    if flagged:
        out["injection_flags"] = flagged
    return out


def _news_fallback(item: dict[str, Any]) -> dict[str, Any]:
    return {"summary": f"{item.get('source_name')} reports: {item.get('headline')}",
            "topic": item.get("topic", "other"), "classification": "unclear",
            "exposure_categories": item.get("exposure_categories", []),
            "household_relevance": "indirect",
            "confidence_note": "Headline-only summary; open the original source for details."}


def _summarize_from_cortex(db: Session | None, item: dict[str, Any], cortex: dict[str, Any]) -> dict[str, Any]:
    title, _ = clean_untrusted(item.get("headline"), 300)
    facts = [clean_untrusted(f.get("statement"), 300)[0] for f in cortex.get("verified_facts", [])]
    uncertain = [clean_untrusted(u, 300)[0] for u in cortex.get("uncertainties", [])]
    prompt = ("Summarise this news item neutrally for a household-finance audience in <= 45 words. Use ONLY the "
              "title and the verified facts below (each was checked against the article text). Use NO numbers, "
              "percentages or dates that do not appear in the verified facts. Mention an uncertainty if relevant. "
              "Classify whether it reports a confirmed event, a forecast, an opinion or speculation. "
              "exposure_categories: household spending categories or asset classes that could be affected "
              "(e.g. transportation, household_bills, food, loan_payments, savings, equities).\n\n"
              f"BEGIN SOURCE id={item.get('id')}\ntitle: {title}\nverified_facts:\n"
              + "\n".join(f"- {f}" for f in facts) + "\nuncertainties:\n" + "\n".join(f"- {u}" for u in uncertain)
              + "\nEND SOURCE")
    out = _run(db, "news", {"id": item.get("id"), "headline": item.get("headline"), "verified_facts": facts,
                            "uncertainties": uncertain, "engine": "cortex-grounded"},
               prompt, NewsSummary, lambda: _news_fallback(item))
    if out["engine"] != FALLBACK_ENGINE:
        allowed = set(_NUM.findall(" ".join([item.get("headline") or "", *facts])))
        used = set(_NUM.findall(out["content"].get("summary", "")))
        if used - allowed:
            log.warning("Gemini news summary used numbers outside Cortex facts %s; using template", sorted(used - allowed))
            out = {"engine": FALLBACK_ENGINE, "content": _news_fallback(item),
                   "fallback_reason": "summary contained numbers not in the verified facts"}
    out["grounded_on"] = "snowflake-cortex"
    return out


def explain_alert(db: Session | None, alert: dict[str, Any], context: dict[str, Any], allow_ai: bool = True) -> dict[str, Any]:
    facts = {"title": alert["title"], "category": alert["category"], "relevance": alert["relevance"],
             "modeled_impact": alert.get("modeled_impact"), "customer": context}
    prompt = ("Explain briefly why this alert is relevant to the customer and suggest one calm, practical "
              f"action. ALERT (authoritative):\n{json.dumps(facts, default=str)}")

    def fb() -> dict[str, Any]:
        return {"explanation": alert["relevance"], "suggested_action": alert["suggested_action"],
                "confidence": "medium"}

    return _run(db, "alert", facts, prompt, AlertExplanation, fb, allow_ai=allow_ai)
