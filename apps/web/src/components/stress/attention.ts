/** Shape of GET /api/insights/needs-attention (staff only). */
export type Flag = "short" | "behind" | "thin";
export interface Attention {
  total: number; matching: number; active_accounts: number; share: number;
  counts: Record<Flag | "green_under_formula", number>;
  items: { account_id: number; flags: Flag[]; balance: number | null; fixed_total: number; left_after_fixed: number | null; B: number; S: number; I: number; loan_status: string | null; runway_ei55: number | null }[];
  rules: Record<Flag, string>; use: string;
}
export const FLAG_LABEL: Record<Flag, string> = { short: "Short this month", behind: "Loan behind", thin: "Under 1 month saved" };
