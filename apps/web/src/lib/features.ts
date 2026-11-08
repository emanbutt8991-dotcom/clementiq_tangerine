/**
 * Central feature registry. Home cards, Settings toggles, categories, the workspace switcher and
 * defaults are all generated from this list. Hiding a feature only changes dashboard visibility —
 * routes, data and background services are untouched, and the backend still enforces permissions.
 */
import type { Role } from "./store";

export type FeatureId =
  | "financialDashboard" | "overview" | "resilienceScore" | "financialTimeline"
  | "shockSimulator" | "recoveryPlans" | "alerts"
  | "investments" | "solanaPortfolio"
  | "worldPulse" | "globalEventMap" | "aiAdvisor" | "insights"
  | "dataImport" | "judgeDemo" | "stressTest" | "needsAttention";

export type CategoryId = "everyday" | "planning" | "investing" | "intelligence" | "data";
export type Palette = "mint" | "peach" | "lavender" | "sky" | "rose" | "butter" | "teal" | "violet" | "coral" | "sage";

export interface Feature {
  id: FeatureId;
  name: string;
  description: string;
  route: string;
  category: CategoryId;
  palette: Palette;
  defaultVisible: boolean;
  /** visible by default for these roles even when defaultVisible is false */
  defaultFor?: Role[];
  order: number;
  /** roles that may use the feature (UI hint only; the API enforces access) */
  roles?: Role[];
  needsAccount: boolean;
  background?: string; // note shown in Settings when hiding does not stop background work
}

export const CATEGORIES: { id: CategoryId; name: string; blurb: string }[] = [
  { id: "everyday", name: "Everyday Finances", blurb: "Your numbers, score and history" },
  { id: "planning", name: "Planning & Protection", blurb: "Stress tests, plans and alerts" },
  { id: "investing", name: "Investing", blurb: "Portfolios and crypto" },
  { id: "intelligence", name: "Intelligence & Discovery", blurb: "World events, AI and insights" },
  { id: "data", name: "Data & Integrations", blurb: "Import status and the judge walkthrough" },
];

export const FEATURES: Feature[] = [
  { id: "financialDashboard", name: "Financial Dashboard", description: "See your complete financial picture in one place.", route: "/dashboard", category: "everyday", palette: "mint", defaultVisible: true, order: 1, needsAccount: true },
  { id: "shockSimulator", name: "Shock Simulator", description: "Test your resilience against life’s financial surprises.", route: "/simulator", category: "planning", palette: "peach", defaultVisible: true, order: 2, needsAccount: true },
  { id: "recoveryPlans", name: "Recovery Plans", description: "Get back on track with personalized action plans.", route: "/recovery", category: "planning", palette: "lavender", defaultVisible: true, order: 3, needsAccount: true },
  { id: "aiAdvisor", name: "AI Financial Advisor", description: "Personalized, data-driven guidance for smarter decisions.", route: "/advisor", category: "intelligence", palette: "teal", defaultVisible: true, order: 4, needsAccount: false },
  { id: "worldPulse", name: "WorldPulse", description: "See how global events could impact your finances.", route: "/worldpulse", category: "intelligence", palette: "sky", defaultVisible: false, order: 13, needsAccount: false,
    background: "Economic data keeps refreshing in the background while hidden." },
  { id: "financialTimeline", name: "Financial Timeline", description: "Your history and a 3D digital twin of your future.", route: "/timeline", category: "everyday", palette: "rose", defaultVisible: false, order: 6, needsAccount: true },
  { id: "investments", name: "Investments & Stocks", description: "Track holdings and stress-test your portfolio.", route: "/investments", category: "investing", palette: "butter", defaultVisible: false, order: 7, needsAccount: false },
  { id: "resilienceScore", name: "Financial Resilience Score", description: "Measure and improve your resilience (0–100).", route: "/resilience", category: "everyday", palette: "violet", defaultVisible: false, order: 8, needsAccount: true },
  { id: "overview", name: "Financial Snapshot", description: "Key numbers, runway and progress at a glance.", route: "/overview", category: "everyday", palette: "sage", defaultVisible: false, order: 9, needsAccount: true },
  { id: "alerts", name: "Alerts & Notifications", description: "Relevant, calm alerts — and how they were scored.", route: "/alerts", category: "planning", palette: "coral", defaultVisible: false, order: 10, needsAccount: false,
    background: "Hiding this card does not stop alerts. Use Notification settings to change what you receive." },
  { id: "globalEventMap", name: "Global Event Map", description: "Explore where economic developments are happening.", route: "/map", category: "intelligence", palette: "sky", defaultVisible: false, order: 11, needsAccount: false },
  { id: "solanaPortfolio", name: "Solana Portfolio", description: "Read-only wallet insights and on-chain goal commitments.", route: "/solana", category: "investing", palette: "violet", defaultVisible: false, order: 12, needsAccount: false },
  { id: "insights", name: "Insights & Discovery", description: "What the data reveals across all customers.", route: "/insights", category: "intelligence", palette: "butter", defaultVisible: true, order: 5, needsAccount: false },
  { id: "judgeDemo", name: "Judge Demo", description: "The full twist-card walkthrough on one screen.", route: "/judge", category: "data", palette: "peach", defaultVisible: false, defaultFor: ["judge"], order: 14, roles: ["judge", "admin"], needsAccount: true },
  { id: "stressTest", name: "Stress Test", description: "Pick an account and a twist card, then read the new runway and both plans.", route: "/stress-test", category: "planning", palette: "coral", defaultVisible: false, defaultFor: ["judge", "admin"], order: 16, roles: ["judge", "admin"], needsAccount: false },
  { id: "needsAttention", name: "Needs Attention", description: "Customers flagged today: short this month, loan behind or thin buffer.", route: "/accounts", category: "planning", palette: "rose", defaultVisible: false, defaultFor: ["judge", "admin"], order: 17, roles: ["judge", "admin"], needsAccount: false },
  { id: "dataImport", name: "Data Import", description: "Ingestion status of the nine challenge datasets.", route: "/admin", category: "data", palette: "mint", defaultVisible: false, order: 15, roles: ["admin", "judge"], needsAccount: false },
];

export const FEATURE_BY_ID = Object.fromEntries(FEATURES.map((f) => [f.id, f])) as Record<FeatureId, Feature>;

export interface DashboardPrefs {
  layout_density: "minimal" | "balanced" | "compact";
  features: Partial<Record<string, boolean>>;
  favorites: string[];
  order: string[];
}

export const DEFAULT_DASHBOARD: DashboardPrefs = { layout_density: "balanced", features: {}, favorites: [], order: [] };

export function available(f: Feature, role: Role | null): boolean {
  return !f.roles || (role != null && f.roles.includes(role));
}

export function isDefaultOn(f: Feature, role: Role | null): boolean {
  return f.defaultVisible || (role != null && !!f.defaultFor?.includes(role));
}

export function isVisible(f: Feature, prefs: DashboardPrefs, role: Role | null): boolean {
  if (!available(f, role)) return false;
  const v = prefs.features[f.id];
  return v === undefined ? isDefaultOn(f, role) : v;
}

/** Ordered list of all features available to the role: custom order first, then registry order. */
export function orderedFeatures(prefs: DashboardPrefs, role: Role | null): Feature[] {
  const pos = new Map(prefs.order.map((id, i) => [id, i]));
  return FEATURES.filter((f) => available(f, role)).sort((a, b) => {
    const pa = pos.has(a.id) ? pos.get(a.id)! : 1000 + a.order;
    const pb = pos.has(b.id) ? pos.get(b.id)! : 1000 + b.order;
    return pa - pb;
  });
}

/** Cards shown on Home: visible only, favorites first (keeping their relative order). */
export function homeFeatures(prefs: DashboardPrefs, role: Role | null): Feature[] {
  const list = orderedFeatures(prefs, role).filter((f) => isVisible(f, prefs, role));
  const fav = new Set(prefs.favorites);
  return [...list.filter((f) => fav.has(f.id)), ...list.filter((f) => !fav.has(f.id))];
}

export function featureForPath(path: string): Feature | undefined {
  return FEATURES.find((f) => path === f.route || path.startsWith(f.route + "/"));
}

/** Explicit visibility map for "Restore defaults" / "Hide optional" / "Enable all". */
export function presetVisibility(kind: "defaults" | "essentials" | "all", role: Role | null): Record<string, boolean> {
  return Object.fromEntries(FEATURES.filter((f) => available(f, role)).map((f) => [
    f.id, kind === "all" ? true : isDefaultOn(f, role),
  ]));
}

/** New full order after the user rearranges the visible cards: visible ids in their new order,
 *  then every other (hidden) feature in its previous position. */
export function reorderedIds(newVisible: string[], prefs: DashboardPrefs, role: Role | null): string[] {
  const rest = orderedFeatures(prefs, role).map((f) => f.id).filter((id) => !newVisible.includes(id));
  return [...newVisible, ...rest];
}

export function toggledFavorites(favorites: string[], id: string): string[] {
  return favorites.includes(id) ? favorites.filter((x) => x !== id) : [...favorites, id];
}
