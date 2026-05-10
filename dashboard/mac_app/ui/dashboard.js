// JARVIS-Dashboard – komplette UI-Logik.
// Stellt die Three.js-Kugel im Zentrum dar, verbindet sich per
// WebSocket mit dem Backend und reagiert auf alle Event-Typen.

import * as THREE from 'three';

const WS_URL = `ws://${location.hostname || '127.0.0.1'}:${location.port || '8080'}/ws`;
const FALLBACK_WS = 'ws://127.0.0.1:8080/ws';

const $ = (id) => document.getElementById(id);

// --- DOM-Referenzen ---
const stateDot      = $('state-dot');
const stateLabel    = $('state-label');
const stateMsg      = $('state-message');
const orbStateLabel = $('orb-state-label');
const clockEl       = $('clock');
const messagesEl    = $('messages');
const composer      = $('composer');
const chatInput     = $('chat-input');
const speakChk      = $('speak-checkbox');
const taskList      = $('task-list');
const tasksCount    = $('tasks-count');
const addTaskForm   = $('add-task-form');
const newTaskInput  = $('new-task');
const cpuEl         = $('cpu');
const cpuBar        = $('cpu-bar');
const ramEl         = $('ram');
const diskEl        = $('disk');
const batteryEl     = $('battery');
const jarvisUptime  = $('jarvis-uptime');
const brainFeed     = $('brain-feed');
const briefingsList = $('briefings-list');
const briefingsCount= $('briefings-count');

const STATE_LABELS = {
  sleeping: 'Schläft', listening: 'Hört zu', thinking: 'Denkt',
  speaking: 'Spricht', error: 'Fehler',     success: 'Bereit',
};

const STATES = {
  sleeping: { color: 0x3a2a8c, accent: 0x6a4ad8, pulseHz: 0.4, scale: 0.95, rotation: 0.08, noise: 0.05 },
  listening:{ color: 0x4ab8ff, accent: 0x9be8ff, pulseHz: 1.6, scale: 1.05, rotation: 0.25, noise: 0.15 },
  thinking: { color: 0x6a8aff, accent: 0xffffff, pulseHz: 1.0, scale: 1.00, rotation: 1.40, noise: 0.20 },
  speaking: { color: 0xffffff, accent: 0x9bf0ff, pulseHz: 3.0, scale: 1.12, rotation: 0.50, noise: 0.35 },
  error:    { color: 0xff3030, accent: 0xff8080, pulseHz: 5.0, scale: 1.00, rotation: 0.15, noise: 0.10 },
  success:  { color: 0x40ff70, accent: 0xc0ffd0, pulseHz: 0.8, scale: 1.05, rotation: 0.25, noise: 0.08 },
};
const DEFAULT_STATE = 'sleeping';

// --- Clock ---
function tickClock() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  clockEl.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
setInterval(tickClock, 1000); tickClock();

// --- Three.js: zentrale Kugel ---
const canvas = $('orb-canvas');
const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
camera.position.set(0, 0, 4.2);

const inner = new THREE.Mesh(
  new THREE.SphereGeometry(0.95, 96, 96),
  new THREE.MeshBasicMaterial({ color: 0x4a3acf }),
);
const wire = new THREE.Mesh(
  new THREE.SphereGeometry(1.15, 32, 20),
  new THREE.MeshBasicMaterial({
    color: 0x9b8aff, wireframe: true, transparent: true, opacity: 0.55,
  }),
);
const halo = new THREE.Mesh(
  new THREE.SphereGeometry(1.65, 48, 48),
  new THREE.MeshBasicMaterial({
    color: 0x4a3acf, transparent: true, opacity: 0.20,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }),
);
const outerHalo = new THREE.Mesh(
  new THREE.SphereGeometry(2.0, 24, 24),
  new THREE.MeshBasicMaterial({
    color: 0x4a3acf, transparent: true, opacity: 0.07,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }),
);
scene.add(outerHalo, halo, inner, wire);

// Partikelfeld um die Kugel
const particleCount = 320;
const particleGeo = new THREE.BufferGeometry();
const positions = new Float32Array(particleCount * 3);
for (let i = 0; i < particleCount; i++) {
  const r = 2.2 + Math.random() * 1.3;
  const theta = Math.random() * Math.PI * 2;
  const phi = Math.acos(2 * Math.random() - 1);
  positions[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
  positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
  positions[i * 3 + 2] = r * Math.cos(phi);
}
particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
const particles = new THREE.Points(
  particleGeo,
  new THREE.PointsMaterial({
    color: 0x9be8ff, size: 0.025, transparent: true, opacity: 0.65,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }),
);
scene.add(particles);

let target = STATES[DEFAULT_STATE];
let speechBoost = 0;  // 0..1, springt während SPEAKING auf 1
let speechDecayUntil = 0;

const animated = {
  color: new THREE.Color(target.color),
  accent: new THREE.Color(target.accent),
  pulseHz: target.pulseHz,
  scale: target.scale,
  rotation: target.rotation,
  noise: target.noise,
};

function setOrbState(name) {
  if (STATES[name]) target = STATES[name];
  orbStateLabel.textContent = (name || '').toUpperCase();
}
setOrbState(DEFAULT_STATE);

function resizeOrb() {
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (w === 0 || h === 0) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resizeOrb).observe(canvas);
resizeOrb();

const clock = new THREE.Clock();
function tick() {
  const dt = clock.getDelta();
  const t = clock.getElapsedTime();
  const k = Math.min(1, dt * 10);

  // Speech-Boost klingt ab
  if (Date.now() > speechDecayUntil) speechBoost = Math.max(0, speechBoost - dt * 0.8);

  animated.color.lerp(new THREE.Color(target.color), k);
  animated.accent.lerp(new THREE.Color(target.accent), k);
  animated.pulseHz += (target.pulseHz - animated.pulseHz) * k;
  animated.scale   += (target.scale   - animated.scale)   * k;
  animated.rotation+= (target.rotation - animated.rotation) * k;
  animated.noise   += (target.noise   - animated.noise)   * k;

  inner.material.color.copy(animated.color);
  halo.material.color.copy(animated.color);
  outerHalo.material.color.copy(animated.color);
  wire.material.color.copy(animated.accent);

  const baseEffect = 0.06 + animated.noise * 0.15;
  const speechExtra = speechBoost * (0.12 + 0.08 * Math.sin(t * 17));
  const pulse = 1 + Math.sin(t * animated.pulseHz * Math.PI * 2) * baseEffect + speechExtra;
  inner.scale.setScalar(animated.scale * pulse);
  halo.scale.setScalar(animated.scale * (1 + Math.sin(t * animated.pulseHz * Math.PI) * 0.10 + speechBoost * 0.1));
  outerHalo.scale.setScalar(animated.scale * (1.05 + Math.sin(t * 0.5) * 0.04));
  wire.rotation.y += animated.rotation * dt;
  wire.rotation.x += animated.rotation * 0.6 * dt;
  particles.rotation.y += dt * 0.08;
  particles.rotation.x += dt * 0.04;

  renderer.render(scene, camera);
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

// --- Speech-Animation ---
function startSpeech(text) {
  // Während des Sprechens pulst die Kugel deutlich stärker; Dauer
  // grob anhand der Textlänge geschätzt (≈ 15 Zeichen/Sekunde).
  const est = Math.max(800, Math.min(text.length * 70, 30000));
  speechBoost = 1.0;
  speechDecayUntil = Date.now() + est;
}
function stopSpeech() {
  speechBoost = 0;
  speechDecayUntil = 0;
}

// --- WebSocket ---
let ws = null;
function connect(url = WS_URL) {
  try { ws = new WebSocket(url); } catch { setTimeout(() => connect(FALLBACK_WS), 1500); return; }
  ws.onopen = () => { stateLabel.textContent = 'Verbunden'; };
  ws.onmessage = (e) => {
    let data; try { data = JSON.parse(e.data); } catch { return; }
    routeMessage(data);
  };
  ws.onclose = () => { stateLabel.textContent = 'getrennt'; setTimeout(() => connect(url), 1500); };
  ws.onerror = () => ws.close();
}
function send(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
}

function routeMessage(data) {
  switch (data.type) {
    case 'state':    onState(data); break;
    case 'chat':     onChat(data);  break;
    case 'history':  onHistory(data); break;
    case 'tasks':    onTasks(data); break;
    case 'system':   onSystem(data); break;
    case 'brain':    onBrain(data); break;
    case 'briefing': onBriefing(data); break;
    case 'activate': onActivate(data); break;
  }
}

// --- Handler ---
function onState({ state, message }) {
  stateDot.dataset.state = state || '';
  stateLabel.textContent = STATE_LABELS[state] || state || '';
  stateMsg.textContent = message || '';
  setOrbState(state);
}

function onHistory({ messages }) {
  messagesEl.innerHTML = '';
  for (const m of messages) addMessage(m);
  scrollChat();
}
function onChat(msg)  { addMessage(msg); scrollChat(); }
function addMessage({ role, content, ts }) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = content;
  if (ts) {
    const t = document.createElement('span'); t.className = 'ts'; t.textContent = formatTs(ts);
    div.appendChild(t);
  }
  messagesEl.appendChild(div);
}
function scrollChat() { messagesEl.scrollTop = messagesEl.scrollHeight; }

function onTasks({ tasks }) {
  taskList.innerHTML = '';
  tasksCount.textContent = tasks.length;
  if (!tasks.length) {
    const li = document.createElement('li'); li.style.opacity = '.5';
    li.textContent = 'Keine offenen Aufgaben.';
    taskList.appendChild(li);
    return;
  }
  for (const t of tasks) {
    const li = document.createElement('li');
    const main = document.createElement('div');
    main.textContent = t.title;
    if (t.due_at) {
      const d = document.createElement('span');
      d.className = 'due'; d.textContent = `fällig ${formatTs(t.due_at)}`;
      main.appendChild(d);
    }
    const btn = document.createElement('button');
    btn.textContent = '✓';
    btn.addEventListener('click', () => send({ type: 'complete_task', task_id: t.id }));
    li.append(main, btn);
    taskList.appendChild(li);
  }
}

function onSystem({ stats }) {
  cpuEl.textContent = stats.cpu || '–';
  ramEl.textContent = stats.ram || '–';
  diskEl.textContent = stats.disk || '–';
  batteryEl.textContent = stats.battery || '–';
  jarvisUptime.textContent = stats.jarvis_uptime || '–';
  const pct = parseInt(stats.cpu, 10);
  if (!isNaN(pct)) cpuBar.style.width = Math.min(100, pct) + '%';
}

function onBrain(data) {
  const li = document.createElement('li');
  li.dataset.kind = data.kind || '';
  li.innerHTML = `
    <span class="ts">${shortTime(data.ts)}</span>
    <span class="kind">${(data.kind || '').replace(/_/g, ' ')}</span>
    <span class="content"></span>
  `;
  li.querySelector('.content').textContent = data.content || '';
  brainFeed.appendChild(li);
  while (brainFeed.children.length > 50) brainFeed.firstChild.remove();
  brainFeed.scrollTop = brainFeed.scrollHeight;

  // Spezial: Speech-Events steuern die Kugel-Animation
  if (data.kind === 'speech_start') startSpeech(data.content || '');
  if (data.kind === 'speech_end')   stopSpeech();
}

function onBriefing({ briefing, unread_total }) {
  if (briefing) {
    const li = document.createElement('li');
    li.innerHTML = `
      <span class="title"></span>
      <span class="ts">${shortTime(new Date().toISOString())}</span>
      <div class="content"></div>
    `;
    li.querySelector('.title').textContent = briefing.title || briefing.agent;
    li.querySelector('.content').textContent = (briefing.content || '').slice(0, 240);
    briefingsList.prepend(li);
    while (briefingsList.children.length > 15) briefingsList.lastChild.remove();
  }
  briefingsCount.textContent = unread_total ?? briefingsList.children.length;
}

function onActivate({ source }) {
  // Backend signalisiert: Aktivierung (Wake-Phrase oder Klatschen).
  // Fenster nach vorne holen und einen kurzen Highlight setzen.
  window.jarvis?.focus?.();
  document.body.animate(
    [
      { boxShadow: 'inset 0 0 80px rgba(74,184,255,0.5)' },
      { boxShadow: 'inset 0 0 0px rgba(74,184,255,0)' },
    ],
    { duration: 900, easing: 'ease-out' },
  );
}

// --- Eingaben ---
composer.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  send({ type: 'chat', content: text, speak: speakChk.checked });
  chatInput.value = '';
});
addTaskForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const title = newTaskInput.value.trim();
  if (!title) return;
  send({ type: 'add_task', title });
  newTaskInput.value = '';
});

// Schnellaktionen
const QUICK_PROMPTS = {
  news:     'Was sind die wichtigsten News heute?',
  weather:  'Wie wird das Wetter heute und morgen?',
  briefings:'Was ist neu? Lies mir die offenen Briefings vor.',
  status:   'Wie ist gerade der Mac-Status?',
  profile:  'Was weißt du eigentlich über mich?',
};
document.querySelectorAll('.quick').forEach((btn) => {
  btn.addEventListener('click', () => {
    const prompt = QUICK_PROMPTS[btn.dataset.action];
    if (prompt) send({ type: 'chat', content: prompt, speak: speakChk.checked });
  });
});

// --- Helfer ---
function formatTs(iso) {
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString('de-DE', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}
function shortTime(iso) {
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  } catch { return ''; }
}

connect();
