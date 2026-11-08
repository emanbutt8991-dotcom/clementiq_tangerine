/** Original soft-3D illustrations for each feature card (inline SVG, no external assets). */
import type { FeatureId } from "@/lib/features";

const Defs = () => (
  <defs>
    <linearGradient id="il-gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffe9a3" /><stop offset="1" stopColor="#e7a922" /></linearGradient>
    <linearGradient id="il-orange" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffc46b" /><stop offset="1" stopColor="#f2700f" /></linearGradient>
    <linearGradient id="il-green" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6fd3a3" /><stop offset="1" stopColor="#1f8a5b" /></linearGradient>
    <linearGradient id="il-violet" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#b9a3ff" /><stop offset="1" stopColor="#6a45dd" /></linearGradient>
    <linearGradient id="il-blue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#8cc4ff" /><stop offset="1" stopColor="#2563eb" /></linearGradient>
    <linearGradient id="il-teal" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6fe0d2" /><stop offset="1" stopColor="#0f8a80" /></linearGradient>
    <linearGradient id="il-rose" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffc3cd" /><stop offset="1" stopColor="#e8506f" /></linearGradient>
    <linearGradient id="il-coral" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffb39c" /><stop offset="1" stopColor="#e5532b" /></linearGradient>
    <linearGradient id="il-sage" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#c6e2a4" /><stop offset="1" stopColor="#5e8f2e" /></linearGradient>
    <linearGradient id="il-screen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#f4fffa" /><stop offset="1" stopColor="#d6f3e6" /></linearGradient>
    <filter id="il-shadow" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#7a3d10" floodOpacity="0.18" /></filter>
  </defs>
);

const Coins = ({ x, y, n = 3 }: { x: number; y: number; n?: number }) => (
  <g>{Array.from({ length: n }, (_, i) => (
    <g key={i}><ellipse cx={x} cy={y - i * 6 + 4} rx="13" ry="5" fill="#c98f14" /><ellipse cx={x} cy={y - i * 6} rx="13" ry="5" fill="url(#il-gold)" /></g>
  ))}</g>
);

const ART: Record<FeatureId, React.ReactNode> = {
  financialDashboard: (<g filter="url(#il-shadow)"><rect x="14" y="14" width="74" height="54" rx="7" fill="#1f5f4a" /><rect x="19" y="19" width="64" height="44" rx="4" fill="url(#il-screen)" />
    <polyline points="24,54 36,44 46,49 58,34 74,28" fill="none" stroke="#18a058" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /><rect x="24" y="24" width="18" height="4" rx="2" fill="#9fdcc0" /><Coins x={96} y={74} n={4} /></g>),
  shockSimulator: (<g filter="url(#il-shadow)"><ellipse cx="60" cy="80" rx="34" ry="9" fill="url(#il-gold)" /><path d="M66 8 L36 50 L56 50 L48 86 L84 38 L62 38 L72 8 Z" fill="url(#il-orange)" stroke="#ffd29a" strokeWidth="2" strokeLinejoin="round" /><Coins x={92} y={80} n={2} /></g>),
  recoveryPlans: (<g filter="url(#il-shadow)"><path d="M18 46 Q60 -2 102 46 Q92 40 81 46 Q70 38 60 46 Q50 38 39 46 Q28 40 18 46 Z" fill="url(#il-violet)" /><path d="M60 46 V80 q0 8 -8 8 q-7 0 -7 -7" fill="none" stroke="#5b3bc4" strokeWidth="4" strokeLinecap="round" /><Coins x={74} y={84} n={3} /></g>),
  worldPulse: (<g filter="url(#il-shadow)"><circle cx="58" cy="50" r="32" fill="url(#il-blue)" /><path d="M36 38 q10 -8 18 0 q6 8 -4 14 q-8 4 -4 12 M66 26 q10 4 8 14 q-4 6 4 12 q8 6 2 14" fill="none" stroke="#bfe0ff" strokeWidth="4" strokeLinecap="round" />
    <path d="M14 76 Q60 52 108 22" fill="none" stroke="#fff" strokeWidth="2.5" opacity="0.9" /><circle cx="44" cy="62" r="4" fill="#fff" /><circle cx="80" cy="40" r="4" fill="#fff" /><circle cx="108" cy="22" r="5" fill="#ffe08a" /></g>),
  financialTimeline: (<g filter="url(#il-shadow)"><path d="M14 54 L40 44 L64 54 L94 44 L104 76 L74 86 L50 76 L24 86 Z" fill="url(#il-rose)" /><path d="M40 44 L50 76 M64 54 L74 86" stroke="#f6a7b6" strokeWidth="2" />
    <path d="M70 10 a14 14 0 0 1 14 14 c0 11 -14 24 -14 24 s-14 -13 -14 -24 a14 14 0 0 1 14 -14 Z" fill="#e23b4e" /><circle cx="70" cy="24" r="5" fill="#fff" /></g>),
  investments: (<g filter="url(#il-shadow)">{[[24, 62, 22], [44, 50, 34], [64, 36, 48], [84, 22, 62]].map(([x, y, h], i) => <rect key={i} x={x} y={y} width="16" height={h} rx="3" fill="url(#il-orange)" />)}
    <path d="M92 22 V12" stroke="#2f8a3a" strokeWidth="3" /><path d="M92 14 q-12 -10 -16 0 q8 6 16 0 Z M92 12 q10 -12 16 -2 q-8 6 -16 2 Z" fill="#43b04b" /></g>),
  aiAdvisor: (<g filter="url(#il-shadow)"><rect x="42" y="12" width="32" height="14" rx="5" fill="none" stroke="#0f6b63" strokeWidth="5" /><rect x="18" y="24" width="80" height="58" rx="10" fill="url(#il-teal)" /><rect x="18" y="44" width="80" height="6" fill="#0d7a71" opacity="0.5" />
    <path d="M84 30 l4 10 l10 4 l-10 4 l-4 10 l-4 -10 l-10 -4 l10 -4 Z" fill="#ffe08a" /></g>),
  resilienceScore: (<g filter="url(#il-shadow)"><path d="M60 8 L94 20 V46 C94 68 78 82 60 90 C42 82 26 68 26 46 V20 Z" fill="url(#il-violet)" /><path d="M44 48 L56 60 L78 36" fill="none" stroke="#fff" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" /></g>),
  overview: (<g filter="url(#il-shadow)"><rect x="26" y="14" width="64" height="74" rx="9" fill="url(#il-sage)" /><rect x="34" y="24" width="48" height="58" rx="5" fill="#f7fbef" />
    <path d="M42 62 a16 16 0 0 1 32 0" fill="none" stroke="#d6e6c3" strokeWidth="7" /><path d="M42 62 a16 16 0 0 1 24 -14" fill="none" stroke="#ff8a1f" strokeWidth="7" strokeLinecap="round" /><rect x="40" y="70" width="36" height="5" rx="2.5" fill="#cfe2b8" /><rect x="46" y="9" width="24" height="10" rx="4" fill="#3f6b1d" /></g>),
  alerts: (<g filter="url(#il-shadow)"><path d="M60 14 c18 0 28 14 28 32 v16 l8 10 H24 l8 -10 V46 c0 -18 10 -32 28 -32 Z" fill="url(#il-coral)" /><circle cx="60" cy="80" r="8" fill="#b8401f" /><circle cx="86" cy="22" r="9" fill="#ffd34d" stroke="#fff" strokeWidth="3" /></g>),
  globalEventMap: (<g filter="url(#il-shadow)"><rect x="14" y="28" width="92" height="56" rx="8" fill="url(#il-blue)" /><path d="M14 46 H106 M14 66 H106 M44 28 V84 M76 28 V84" stroke="#bcdcff" strokeWidth="1.5" opacity="0.7" />
    {[[36, 50], [62, 62], [88, 44]].map(([x, y], i) => <g key={i}><path d={`M${x} ${y - 20} a9 9 0 0 1 9 9 c0 7 -9 15 -9 15 s-9 -8 -9 -15 a9 9 0 0 1 9 -9 Z`} fill={i === 1 ? "#ff8a1f" : "#fff"} /><circle cx={x} cy={y - 11} r="3" fill={i === 1 ? "#fff" : "#2563eb"} /></g>)}</g>),
  solanaPortfolio: (<g filter="url(#il-shadow)">{[0, 1, 2].map((i) => <path key={i} d={`M${30 + (i === 1 ? 8 : 0)} ${26 + i * 22} H${88 + (i === 1 ? -8 : 0)} l-10 12 H${20 + (i === 1 ? 8 : 0)} Z`} fill="url(#il-violet)" opacity={1 - i * 0.12} />)}<Coins x={96} y={84} n={2} /></g>),
  insights: (<g filter="url(#il-shadow)"><path d="M60 10 a28 28 0 0 1 16 51 v9 H44 v-9 A28 28 0 0 1 60 10 Z" fill="url(#il-gold)" /><rect x="44" y="72" width="32" height="8" rx="3" fill="#b9a37a" /><rect x="48" y="82" width="24" height="7" rx="3" fill="#9c8762" />
    <path d="M52 50 l8 -12 l8 12" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />{[[20, 26], [100, 26], [14, 52], [106, 52]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3.5" fill="#ffb84d" />)}</g>),
  dataImport: (<g filter="url(#il-shadow)">{[60, 42, 24].map((y, i) => <g key={i}><path d={`M28 ${y} v14 a32 10 0 0 0 64 0 v-14`} fill={i === 2 ? "url(#il-green)" : "#2a9a68"} /><ellipse cx="60" cy={y} rx="32" ry="10" fill={i === 2 ? "#b5ecd2" : "url(#il-green)"} /></g>)}
    <path d="M96 30 v26 m-8 -8 l8 8 l8 -8" fill="none" stroke="#ff8a1f" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /></g>),
  stressTest: (<g filter="url(#il-shadow)"><path d="M18 70 A42 42 0 0 1 102 70" fill="none" stroke="url(#il-coral)" strokeWidth="12" strokeLinecap="round" /><path d="M60 70 L82 40" stroke="#7a2a12" strokeWidth="5" strokeLinecap="round" /><circle cx="60" cy="70" r="7" fill="#7a2a12" /><Coins x={98} y={86} n={2} /></g>),
  needsAttention: (<g filter="url(#il-shadow)"><rect x="20" y="16" width="62" height="70" rx="8" fill="url(#il-rose)" />{[32, 50, 68].map((y, i) => <g key={y}><circle cx="34" cy={y} r="5" fill={i === 0 ? "#9b1f3a" : "#fff3f5"} /><rect x="44" y={y - 3} width="28" height="6" rx="3" fill="#fff3f5" /></g>)}<circle cx="92" cy="26" r="12" fill="url(#il-orange)" /><rect x="90" y="18" width="4" height="10" rx="2" fill="#fff" /><circle cx="92" cy="32" r="2" fill="#fff" /></g>),
  judgeDemo: (<g filter="url(#il-shadow)"><rect x="18" y="74" width="60" height="12" rx="4" fill="url(#il-orange)" /><g transform="rotate(-35 64 40)"><rect x="40" y="24" width="48" height="22" rx="6" fill="#9a5b2e" /><rect x="60" y="44" width="8" height="40" rx="3" fill="#c98a55" /></g><Coins x={98} y={84} n={2} /></g>),
};

export function FeatureIllustration({ id, size = 84 }: { id: FeatureId; size?: number }) {
  return (
    <svg viewBox="0 0 120 96" width={size * 1.25} height={size} aria-hidden className="shrink-0">
      <Defs />
      {ART[id]}
    </svg>
  );
}
