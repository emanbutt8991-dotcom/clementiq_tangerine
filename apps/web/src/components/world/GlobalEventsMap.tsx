"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { usePrefersReducedMotion } from "@/lib/hooks";
import { Skeleton } from "@/components/ui/misc";
import type { GlobeMarker } from "./GlobeScene";
import { ISO3_TO_NUM, MAP_COLORS, countries, countryPath, projX, projY } from "./worldGeo";

const GlobeScene = dynamic(() => import("./GlobeScene"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

const W = 720, H = 360;

/** 2D equirectangular map: Natural Earth country outlines, countries with events tinted, markers pulsing. */
function FlatMap({ markers, selected, onSelect, animate }: { markers: GlobeMarker[]; selected: string | null; onSelect: (iso3: string) => void; animate: boolean }) {
  const active = useMemo(() => new Set(markers.filter((m) => m.count > 0).map((m) => ISO3_TO_NUM[m.iso3])), [markers]);
  // Keyed by position: a few disputed territories (Kosovo, N. Cyprus, Somaliland) have no id in the atlas.
  const shapes = useMemo(() => countries().map((c, i) => ({ key: `${i}-${c.id}`, id: c.id, name: c.name, d: countryPath(c, W, H) })), []);
  const x = (lon: number) => projX(lon, W);
  const y = (lat: number) => projY(lat, H);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" role="img" aria-label="Flat map of economic developments" preserveAspectRatio="xMidYMid meet">
      <rect width={W} height={H} fill={MAP_COLORS.ocean} />
      {[-60, -30, 0, 30, 60].map((lat) => <line key={lat} x1={0} x2={W} y1={y(lat)} y2={y(lat)} stroke={MAP_COLORS.grid} strokeOpacity={0.15} strokeWidth={0.5} />)}
      {Array.from({ length: 12 }, (_, i) => i * 30 - 180).map((lon) => <line key={lon} y1={0} y2={H} x1={x(lon)} x2={x(lon)} stroke={MAP_COLORS.grid} strokeOpacity={0.15} strokeWidth={0.5} />)}
      {shapes.map((s) => {
        const on = active.has(s.id);
        return <path key={s.key} d={s.d} fillRule="evenodd" fill={on ? MAP_COLORS.active : MAP_COLORS.land} stroke={on ? MAP_COLORS.activeBorder : MAP_COLORS.border} strokeWidth={on ? 0.8 : 0.4}><title>{s.name}</title></path>;
      })}
      {markers.map((m, i) => {
        const cx = x(m.lon), cy = y(m.lat);
        const r = 3.5 + Math.min(m.count, 20) * 0.3;
        const color = m.count ? MAP_COLORS.event : MAP_COLORS.indicator;
        const dim = selected && selected !== m.iso3;
        return (
          <g key={m.iso3} onClick={() => onSelect(m.iso3)} className="cursor-pointer" role="button" aria-label={`${m.name}: ${m.count} events`} tabIndex={0}
             onKeyDown={(e) => e.key === "Enter" && onSelect(m.iso3)} opacity={dim ? 0.45 : 1}>
            <circle cx={cx} cy={cy} r={14} fill="transparent" />
            {animate ? (
              <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={1.5}>
                <animate attributeName="r" from={r} to={r * 4} dur="2s" begin={`${(i % 5) * 0.4}s`} repeatCount="indefinite" />
                <animate attributeName="opacity" from={0.9} to={0} dur="2s" begin={`${(i % 5) * 0.4}s`} repeatCount="indefinite" />
              </circle>
            ) : <circle cx={cx} cy={cy} r={r * 2} fill="none" stroke={color} strokeWidth={1} opacity={0.5} />}
            <circle cx={cx} cy={cy} r={r} fill={selected === m.iso3 ? "#ffffff" : color} stroke={MAP_COLORS.oceanEdge} strokeWidth={1} />
            <text x={cx + r + 4} y={cy + 3.5} fontSize={10} fontWeight={600} fill="#dbe7f5">{m.iso3}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function GlobalEventsMap({ markers, selected, onSelect, prefer3d = true }: { markers: GlobeMarker[]; selected: string | null; onSelect: (iso3: string) => void; prefer3d?: boolean }) {
  const reduced = usePrefersReducedMotion();
  const [webgl, setWebgl] = useState(true);
  const [mode, setMode] = useState<"3d" | "2d">("3d");
  useEffect(() => {
    try { const c = document.createElement("canvas"); setWebgl(!!(c.getContext("webgl2") || c.getContext("webgl"))); } catch { setWebgl(false); }
  }, []);
  const use3d = prefer3d && webgl && mode === "3d";
  const withEvents = markers.filter((m) => m.count > 0).length;
  return (
    <div className="relative h-[420px] w-full overflow-hidden rounded-2xl"
      style={{ background: `radial-gradient(ellipse at 50% 40%, #12305a 0%, ${MAP_COLORS.oceanEdge} 55%, #03070d 100%)` }}>
      {use3d
        ? <GlobeScene markers={markers} selected={selected} onSelect={onSelect} autoRotate={!reduced} animate={!reduced} />
        : <FlatMap markers={markers} selected={selected} onSelect={onSelect} animate={!reduced} />}
      <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/45 px-3 py-1 text-[0.6875rem] font-semibold text-white backdrop-blur">
        <span className="relative flex size-2">
          {!reduced && <span className="absolute inline-flex size-full animate-ping rounded-full bg-[#ff7a1a] opacity-75" />}
          <span className="relative inline-flex size-2 rounded-full bg-[#ff7a1a]" />
        </span>
        {markers.length} countries · {withEvents} with news
      </div>
      <div className="absolute right-3 top-3 flex gap-1 rounded-xl bg-black/45 p-1 text-[0.6875rem] font-semibold backdrop-blur">
        {(["3d", "2d"] as const).map((m) => (
          <button key={m} disabled={m === "3d" && !webgl} onClick={() => setMode(m)} aria-pressed={mode === m}
            className={`cursor-pointer rounded-lg px-2 py-1 ${mode === m ? "bg-white/90 text-tangerine" : "text-white/80"} disabled:opacity-40`}>{m.toUpperCase()}</button>
        ))}
      </div>
    </div>
  );
}
