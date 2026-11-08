/**
 * Country outlines for the Global Event Map (Natural Earth 1:110m via the world-atlas package).
 * Bundled with the app, so the map draws offline. Coordinates are lon/lat; both the globe texture and
 * the flat SVG use the same equirectangular projection: x = (lon + 180) / 360, y = (90 - lat) / 180.
 */
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import atlas from "world-atlas/countries-110m.json";

export type Ring = [number, number][];
export interface Country { id: string; name: string; rings: Ring[] }

/** ISO 3166 alpha-3 → numeric id used by world-atlas, for the countries WorldPulse places markers on. */
export const ISO3_TO_NUM: Record<string, string> = {
  CAN: "124", USA: "840", MEX: "484", GBR: "826", DEU: "276", FRA: "250", CHN: "156", JPN: "392",
  IND: "356", BRA: "076", SAU: "682", KOR: "410", AUS: "036", ZAF: "710", NGA: "566",
};

/**
 * Make a ring's longitudes continuous, so a shape crossing the antimeridian (Russia, Fiji) does not
 * draw a stripe across the whole map. Callers draw each ring at offsets -360, 0 and +360 and let the
 * canvas or SVG clip it. Rings that wrap all the way round a pole (Antarctica) are closed via the pole.
 */
export function unwrap(ring: number[][]): Ring {
  const out: Ring = [];
  let shift = 0;
  let prev: number | null = null;
  for (const [lon, lat] of ring) {
    let l = lon + shift;
    if (prev != null) {
      while (l - prev > 180) { shift -= 360; l -= 360; }
      while (prev - l > 180) { shift += 360; l += 360; }
    }
    out.push([l, lat]);
    prev = l;
  }
  if (out.length > 1 && Math.abs(out[out.length - 1][0] - out[0][0]) >= 359) {
    const pole = out.reduce((s, p) => s + p[1], 0) / out.length < 0 ? -90 : 90;
    out.push([out[out.length - 1][0], pole], [out[0][0], pole]);
  }
  return out;
}

let cache: Country[] | null = null;
export function countries(): Country[] {
  if (cache) return cache;
  const topo = atlas as unknown as Topology<{ countries: GeometryCollection<{ name: string }> }>;
  const fc = feature(topo, topo.objects.countries);
  cache = fc.features.map((f) => {
    const g = f.geometry;
    const polys: number[][][][] = g?.type === "Polygon" ? [g.coordinates] : g?.type === "MultiPolygon" ? g.coordinates : [];
    return { id: String(f.id), name: f.properties?.name ?? "", rings: polys.flat().map(unwrap) };
  });
  return cache;
}

export const OFFSETS = [-360, 0, 360] as const;
export const projX = (lon: number, w: number) => ((lon + 180) / 360) * w;
export const projY = (lat: number, h: number) => ((90 - lat) / 180) * h;

/** SVG path data for one country in a w×h equirectangular frame, including the wrapped copies. */
export function countryPath(c: Country, w: number, h: number): string {
  let d = "";
  for (const off of OFFSETS) for (const r of c.rings) {
    r.forEach(([lon, lat], i) => { d += `${i ? "L" : "M"}${projX(lon + off, w).toFixed(1)} ${projY(lat, h).toFixed(1)}`; });
    d += "Z";
  }
  return d;
}

/** Map palette: a dark "operations" look, so glowing markers read as live activity. Fixed in both themes. */
export const MAP_COLORS = {
  ocean: "#0b1d33", oceanEdge: "#06111f", land: "#1f3a5c", border: "#3d6591", active: "#7a3d1c", activeBorder: "#ff8a3d",
  grid: "#5b86b8", event: "#ff7a1a", indicator: "#a78bfa", glow: "#4ea8ff",
} as const;

/** Paint the world onto a canvas (used as the globe's texture). `active` = world-atlas ids to tint. */
export function paintWorld(canvas: HTMLCanvasElement, active: Set<string>): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const { width: w, height: h } = canvas;
  const sea = ctx.createLinearGradient(0, 0, 0, h);
  sea.addColorStop(0, MAP_COLORS.oceanEdge); sea.addColorStop(0.5, MAP_COLORS.ocean); sea.addColorStop(1, MAP_COLORS.oceanEdge);
  ctx.fillStyle = sea;
  ctx.fillRect(0, 0, w, h);
  ctx.lineJoin = "round";
  for (const c of countries()) {
    const on = active.has(c.id);
    ctx.beginPath();
    for (const off of OFFSETS) for (const r of c.rings) {
      r.forEach(([lon, lat], i) => (i ? ctx.lineTo : ctx.moveTo).call(ctx, projX(lon + off, w), projY(lat, h)));
      ctx.closePath();
    }
    ctx.fillStyle = on ? MAP_COLORS.active : MAP_COLORS.land;
    ctx.fill("evenodd");
    ctx.strokeStyle = on ? MAP_COLORS.activeBorder : MAP_COLORS.border;
    ctx.lineWidth = on ? 2 : 1;
    ctx.stroke();
  }
}
