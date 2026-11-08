import { describe, expect, it } from "vitest";
import { DEFAULT_DASHBOARD, FEATURES, homeFeatures, isVisible, orderedFeatures, presetVisibility, reorderedIds, toggledFavorites, type DashboardPrefs } from "./features";
import { growthFromSummary, DECORATIVE_GROWTH } from "./growth";

const ids = (fs: { id: string }[]) => fs.map((f) => f.id);
const prefs = (p: Partial<DashboardPrefs>): DashboardPrefs => ({ ...DEFAULT_DASHBOARD, ...p });

describe("feature registry", () => {
  it("has unique ids and routes", () => {
    expect(new Set(ids(FEATURES)).size).toBe(FEATURES.length);
    expect(new Set(FEATURES.map((f) => f.route)).size).toBe(FEATURES.length);
  });

  // The rubric's three tasks (know the customer, take a shock, make a plan), Communication (advisor)
  // and Discovery, the biggest judging weight (insights).
  it("new users see the five rubric tools by default", () => {
    expect(ids(homeFeatures(DEFAULT_DASHBOARD, "customer"))).toEqual(["financialDashboard", "shockSimulator", "recoveryPlans", "aiAdvisor", "insights"]);
  });

  it("judges also get the Judge Demo by default; Data Import is never shown to customers", () => {
    expect(ids(homeFeatures(DEFAULT_DASHBOARD, "judge"))).toContain("judgeDemo");
    const all = prefs({ features: presetVisibility("all", "customer") });
    expect(ids(homeFeatures(all, "customer"))).not.toContain("dataImport");
    expect(ids(orderedFeatures(DEFAULT_DASHBOARD, "admin"))).toContain("dataImport");
  });

  it("Judge Demo can never appear for customers, even if a preference says so", () => {
    const forced = prefs({ features: { judgeDemo: true }, favorites: ["judgeDemo"] });
    expect(ids(homeFeatures(forced, "customer"))).not.toContain("judgeDemo");
    expect(ids(orderedFeatures(forced, "customer"))).not.toContain("judgeDemo");
    expect(ids(homeFeatures(DEFAULT_DASHBOARD, null))).not.toContain("judgeDemo");
    expect(ids(homeFeatures(DEFAULT_DASHBOARD, "admin"))).not.toContain("judgeDemo"); // available, but off by default
    expect(ids(orderedFeatures(DEFAULT_DASHBOARD, "admin"))).toContain("judgeDemo");
  });

  it("hiding removes a card and the rest close the gap; re-enabling restores it", () => {
    const hidden = prefs({ features: { shockSimulator: false } });
    expect(ids(homeFeatures(hidden, "customer"))).toEqual(["financialDashboard", "recoveryPlans", "aiAdvisor", "insights"]);
    const back = prefs({ features: { shockSimulator: true } });
    expect(ids(homeFeatures(back, "customer"))).toContain("shockSimulator");
  });

  it("explicit choices win over defaults and unknown ids are ignored", () => {
    const p = prefs({ features: { worldPulse: true, financialDashboard: false, notAFeature: true } });
    const home = ids(homeFeatures(p, "customer"));
    expect(home).toContain("worldPulse");
    expect(home).not.toContain("financialDashboard");
    expect(home).not.toContain("notAFeature");
  });

  it("favorites come first, then the custom order", () => {
    const p = prefs({ order: ["aiAdvisor", "recoveryPlans", "shockSimulator", "financialDashboard"], favorites: ["shockSimulator"] });
    expect(ids(homeFeatures(p, "customer"))).toEqual(["shockSimulator", "aiAdvisor", "recoveryPlans", "financialDashboard", "insights"]);
    expect(toggledFavorites(["a"], "a")).toEqual([]);
    expect(toggledFavorites([], "a")).toEqual(["a"]);
  });

  it("reordering keeps hidden features after the visible ones", () => {
    const order = reorderedIds(["aiAdvisor", "financialDashboard"], DEFAULT_DASHBOARD, "customer");
    expect(order.slice(0, 2)).toEqual(["aiAdvisor", "financialDashboard"]);
    expect(new Set(order).size).toBe(order.length);
    expect(order).toContain("worldPulse");
  });

  it("everything off → empty home (empty state), nothing is lost", () => {
    const none = prefs({ features: Object.fromEntries(FEATURES.map((f) => [f.id, false])) });
    expect(homeFeatures(none, "judge")).toHaveLength(0);
    expect(isVisible(FEATURES[0], prefs({}), "judge")).toBe(true);
  });
});

describe("orchard growth", () => {
  it("is decorative without data and data-driven with it", () => {
    expect(growthFromSummary(undefined)).toBe(DECORATIVE_GROWTH);
    const s = { metrics: { emergency_fund_progress: 1, coverage_months: 6.4, avg_monthly_cash_flow: -50 }, resilience: { score: 72 } };
    const g = growthFromSummary(s as never);
    expect(g.golden).toBe(2);
    expect(g.fruit).toBe(1);
    expect(g.milestone).toBe(4);
    expect(g.vibrance).toBeGreaterThan(0.5);
  });
});
