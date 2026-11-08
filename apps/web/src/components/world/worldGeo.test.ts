import { describe, expect, it } from "vitest";
import { ISO3_TO_NUM, countries, countryPath, unwrap } from "./worldGeo";

describe("world map geometry", () => {
  it("loads the Natural Earth countries, including every country WorldPulse marks", () => {
    const cs = countries();
    expect(cs.length).toBeGreaterThan(150);
    const ids = new Set(cs.map((c) => c.id));
    for (const num of Object.values(ISO3_TO_NUM)) expect(ids).toContain(num);
  });

  it("no ring jumps across the map (antimeridian handled), so no stripes", () => {
    for (const c of countries()) for (const r of c.rings) for (let i = 1; i < r.length; i++) {
      const alongPole = Math.abs(r[i][1]) === 90 && r[i][1] === r[i - 1][1]; // map's top/bottom edge, e.g. under Antarctica
      if (!alongPole) expect(Math.abs(r[i][0] - r[i - 1][0])).toBeLessThanOrEqual(180);
    }
  });

  it("unwraps a ring that crosses 180°", () => {
    expect(unwrap([[179, 0], [-179, 1], [-178, 0]])).toEqual([[179, 0], [181, 1], [182, 0]]);
  });

  it("closes a ring that circles a pole through the pole", () => {
    const ring = Array.from({ length: 37 }, (_, i) => [i * 10 - 180, -70]);
    const out = unwrap(ring);
    expect(out.at(-1)).toEqual([-180, -90]);
    expect(out.at(-2)).toEqual([180, -90]);
  });

  it("produces finite SVG path data", () => {
    const can = countries().find((c) => c.id === ISO3_TO_NUM.CAN)!;
    const d = countryPath(can, 720, 360);
    expect(d.startsWith("M")).toBe(true);
    expect(d).not.toMatch(/NaN|Infinity/);
  });
});
