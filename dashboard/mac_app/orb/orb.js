// JARVIS-Kugel: drei verschachtelte Three.js-Kugeln (solider Kern,
// rotierende Wireframe-Schale, additiver Halo) mit weicher Animation
// zwischen den Zuständen aus states.js.
//
// Verbindet sich mit dem Python-WebSocket auf ws://127.0.0.1:8765 und
// reagiert auf Zustandsänderungen. Ein "echter" Klick (kein Drag)
// öffnet das Dashboard via Preload-Bridge.

import * as THREE from 'three';
import { STATES, DEFAULT_STATE } from './states.js';

const WS_URL = 'ws://127.0.0.1:8080/ws';
const canvas = document.getElementById('orb');

// --- Three.js-Setup ---
const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight, false);
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
camera.position.set(0, 0, 4);

const inner = new THREE.Mesh(
  new THREE.SphereGeometry(0.9, 64, 64),
  new THREE.MeshBasicMaterial({ color: 0x4a3acf }),
);
const wire = new THREE.Mesh(
  new THREE.SphereGeometry(1.12, 24, 16),
  new THREE.MeshBasicMaterial({
    color: 0x9b8aff, wireframe: true, transparent: true, opacity: 0.45,
  }),
);
const halo = new THREE.Mesh(
  new THREE.SphereGeometry(1.55, 32, 32),
  new THREE.MeshBasicMaterial({
    color: 0x4a3acf, transparent: true, opacity: 0.18,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }),
);
scene.add(halo, inner, wire);

// --- State-Animation ---
const animated = {
  color: new THREE.Color(STATES[DEFAULT_STATE].color),
  accent: new THREE.Color(STATES[DEFAULT_STATE].accent),
  pulseHz: STATES[DEFAULT_STATE].pulseHz,
  scale: STATES[DEFAULT_STATE].scale,
  rotation: STATES[DEFAULT_STATE].rotation,
};
let target = STATES[DEFAULT_STATE];

function setState(name) {
  if (STATES[name]) target = STATES[name];
}

const clock = new THREE.Clock();
function tick() {
  const dt = clock.getDelta();
  const t = clock.getElapsedTime();
  const k = Math.min(1, dt * 4);

  animated.color.lerp(new THREE.Color(target.color), k);
  animated.accent.lerp(new THREE.Color(target.accent), k);
  animated.pulseHz += (target.pulseHz - animated.pulseHz) * k;
  animated.scale += (target.scale - animated.scale) * k;
  animated.rotation += (target.rotation - animated.rotation) * k;

  inner.material.color.copy(animated.color);
  halo.material.color.copy(animated.color);
  wire.material.color.copy(animated.accent);

  const pulse = 1 + Math.sin(t * animated.pulseHz * Math.PI * 2) * 0.06;
  inner.scale.setScalar(animated.scale * pulse);
  halo.scale.setScalar(animated.scale * (1 + Math.sin(t * animated.pulseHz * Math.PI) * 0.10));
  wire.rotation.y += animated.rotation * dt;
  wire.rotation.x += animated.rotation * 0.6 * dt;

  renderer.render(scene, camera);
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

window.addEventListener('resize', () => {
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
});

// --- WebSocket: Zustand vom Python-Backend ---
function connect() {
  const ws = new WebSocket(WS_URL);
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      // Nur State-Events interessieren die Kugel; alles andere ignorieren.
      if (data && (!data.type || data.type === 'state') && data.state) {
        setState(data.state);
      }
    } catch { /* ignorieren */ }
  };
  ws.onclose = () => setTimeout(connect, 1500);
  ws.onerror = () => ws.close();
}
connect();

// --- Drag und Klick (nicht via CSS-Drag-Region, weil macOS die Maus-Events
//     in Drag-Regions schluckt). Wir tracken in JS und delegieren das
//     Verschieben an den Hauptprozess via IPC.
let press = null;
let dragging = false;
const DRAG_THRESHOLD_PX = 4;

window.addEventListener('mousedown', (e) => {
  press = { x: e.screenX, y: e.screenY, t: Date.now() };
  dragging = false;
  window.jarvis?.dragStart?.(e.screenX, e.screenY);
});
window.addEventListener('mousemove', (e) => {
  if (!press) return;
  const dist = Math.hypot(e.screenX - press.x, e.screenY - press.y);
  if (!dragging && dist > DRAG_THRESHOLD_PX) dragging = true;
  if (dragging) window.jarvis?.drag?.(e.screenX, e.screenY);
});
window.addEventListener('mouseup', (e) => {
  if (!press) return;
  const dur = Date.now() - press.t;
  const wasDragging = dragging;
  press = null;
  dragging = false;
  window.jarvis?.dragEnd?.();
  // Wenn nicht gedraggt wurde und der Klick kurz war: Dashboard öffnen.
  if (!wasDragging && dur < 500) {
    window.jarvis?.openDashboard?.();
  }
});
