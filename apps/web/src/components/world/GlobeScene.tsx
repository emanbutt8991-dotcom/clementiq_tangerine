"use client";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { ISO3_TO_NUM, MAP_COLORS, paintWorld } from "./worldGeo";

export interface GlobeMarker { iso3: string; name: string; lat: number; lon: number; count: number; hasIndicators: boolean }

export function latLonToVec3(lat: number, lon: number, r: number): [number, number, number] {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((lon + 180) * Math.PI) / 180;
  return [-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)];
}

/** Countries painted onto a canvas and wrapped round the sphere (same lon/lat mapping as latLonToVec3). */
function useWorldTexture(activeKey: string) {
  const tex = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 2048; canvas.height = 1024;
    paintWorld(canvas, new Set(activeKey ? activeKey.split(",") : []));
    const t = new THREE.CanvasTexture(canvas);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 8;
    return t;
  }, [activeKey]);
  useEffect(() => () => tex.dispose(), [tex]);
  return tex;
}

function Graticule() {
  const lines = useMemo(() => {
    const out: [number, number, number][][] = [];
    for (let lat = -60; lat <= 60; lat += 30) out.push(Array.from({ length: 73 }, (_, i) => latLonToVec3(lat, i * 5 - 180, 2.004)));
    for (let lon = -180; lon < 180; lon += 30) out.push(Array.from({ length: 37 }, (_, i) => latLonToVec3(i * 5 - 90, lon, 2.004)));
    return out;
  }, []);
  return <>{lines.map((pts, i) => <Line key={i} points={pts} color={MAP_COLORS.grid} lineWidth={0.5} transparent opacity={0.18} />)}</>;
}

/** Soft blue rim light around the planet (fresnel on a slightly larger back-facing sphere). */
function Atmosphere() {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    uniforms: { glow: { value: new THREE.Color(MAP_COLORS.glow) } },
    vertexShader: "varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: "uniform vec3 glow; varying vec3 vN; void main(){ float i = pow(0.7 - dot(vN, vec3(0.0, 0.0, 1.0)), 3.0); gl_FragColor = vec4(glow, 1.0) * i; }",
    side: THREE.BackSide, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false,
  }), []);
  useEffect(() => () => mat.dispose(), [mat]);
  return <mesh material={mat} scale={1.16}><sphereGeometry args={[2, 64, 64]} /></mesh>;
}

/** Expanding ring that fades out, repeated: reads as "something is happening here". */
function Pulse({ color, size, phase, animate }: { color: string; size: number; phase: number; animate: boolean }) {
  const ring = useRef<THREE.Mesh>(null);
  const mat = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }) => {
    if (!ring.current || !mat.current) return;
    const t = animate ? ((clock.elapsedTime * 0.5 + phase) % 1) : 0.35;
    ring.current.scale.setScalar(1 + t * 3.2);
    mat.current.opacity = 0.85 * (1 - t);
  });
  return (
    <mesh ref={ring}>
      <ringGeometry args={[size * 1.1, size * 1.45, 40]} />
      <meshBasicMaterial ref={mat} color={color} transparent depthWrite={false} side={THREE.DoubleSide} />
    </mesh>
  );
}

function Marker({ m, selected, onSelect, animate }: { m: GlobeMarker; selected: boolean; onSelect: (iso3: string) => void; animate: boolean }) {
  const [hover, setHover] = useState(false);
  const g = useRef<THREE.Group>(null);
  const pos = useMemo(() => latLonToVec3(m.lat, m.lon, 2.012), [m.lat, m.lon]);
  // Face the group outward, so the pulse rings lie flat on the surface.
  useLayoutEffect(() => { g.current?.lookAt(pos[0] * 2, pos[1] * 2, pos[2] * 2); }, [pos]);
  const size = 0.03 + Math.min(m.count, 20) * 0.004;
  const color = m.count ? MAP_COLORS.event : MAP_COLORS.indicator;
  const phase = useMemo(() => (m.iso3.charCodeAt(0) * 7 + m.iso3.charCodeAt(2)) % 100 / 100, [m.iso3]);
  const big = hover || selected;
  return (
    <group ref={g} position={pos}>
      <Pulse color={color} size={size} phase={phase} animate={animate} />
      {m.count > 0 && <Pulse color={color} size={size} phase={phase + 0.5} animate={animate} />}
      <mesh onClick={(e) => { e.stopPropagation(); onSelect(m.iso3); }}
        onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { setHover(false); document.body.style.cursor = ""; }}>
        <sphereGeometry args={[size * (big ? 1.6 : 1), 20, 20]} />
        <meshBasicMaterial color={selected ? "#ffffff" : color} toneMapped={false} />
      </mesh>
      {big && (
        <Html distanceFactor={7} center position={[0, 0, 0.12]} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded-lg bg-white px-2 py-1 text-[0.6875rem] font-semibold text-slate-900 shadow">{m.name} · {m.count} events{m.hasIndicators ? " · indicators" : ""}</div>
        </Html>
      )}
    </group>
  );
}

function Spin({ children, enabled }: { children: React.ReactNode; enabled: boolean }) {
  const g = useRef<THREE.Group>(null);
  // Start with the Americas facing the viewer: Canada is where most events are.
  useLayoutEffect(() => { if (g.current) g.current.rotation.y = -0.6; }, []);
  useFrame((_, dt) => { if (enabled && g.current) g.current.rotation.y += dt * 0.05; });
  return <group ref={g}>{children}</group>;
}

export default function GlobeScene({ markers, selected, onSelect, autoRotate, animate = true }: { markers: GlobeMarker[]; selected: string | null; onSelect: (iso3: string) => void; autoRotate: boolean; animate?: boolean }) {
  const activeKey = markers.filter((m) => m.count > 0).map((m) => ISO3_TO_NUM[m.iso3]).filter(Boolean).sort().join(",");
  const tex = useWorldTexture(activeKey);
  return (
    <Canvas camera={{ position: [0, 1.2, 5.4], fov: 45 }} dpr={[1, 2]} aria-label="3D globe of economic developments">
      <ambientLight intensity={1.1} />
      <directionalLight position={[5, 3, 5]} intensity={1.6} />
      <Spin enabled={autoRotate && !selected}>
        <mesh>
          <sphereGeometry args={[2, 96, 96]} />
          <meshStandardMaterial map={tex} emissiveMap={tex} emissive="#ffffff" emissiveIntensity={0.35} roughness={0.85} metalness={0} />
        </mesh>
        <Graticule />
        {markers.map((m) => <Marker key={m.iso3} m={m} selected={selected === m.iso3} onSelect={onSelect} animate={animate} />)}
      </Spin>
      <Atmosphere />
      <OrbitControls enablePan={false} minDistance={3.2} maxDistance={9} />
    </Canvas>
  );
}
