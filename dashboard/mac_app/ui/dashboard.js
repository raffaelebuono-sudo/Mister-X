// JARVIS Dashboard – cinematic HUD.
// Die 3D-Kugel (Three.js) wird dynamisch und fehlertolerant geladen:
// schlägt sie fehl (z. B. kein Netz), läuft das restliche Dashboard
// trotzdem komplett weiter.

const WS_URL = `ws://${location.hostname || '127.0.0.1'}:${location.port || '8080'}/ws`;
const $ = (id) => document.getElementById(id);

// Orb-API – von initOrb() befüllt; vorher No-Ops.
const orb = { setState() {}, startSpeech() {}, stopSpeech() {} };
function setOrbState(name) {
  const lbl = $('orb-state-label'); if (lbl) lbl.textContent = (name || '').toUpperCase();
  const ro = $('ro-state'); if (ro) ro.textContent = 'CORE: ' + (name || '').toUpperCase();
  orb.setState(name);
}
function startSpeech(t) { orb.startSpeech(t); }
function stopSpeech() { orb.stopSpeech(); }

// ---------- Boot-Sequenz ----------
const bootEl = $('boot');
const bootLines = $('boot-lines');
const bootBar = $('boot-bar-fill');
const BOOT_STEPS = [
  'Initialisiere Kern …',
  'Lade neuronale Verbindungen …',
  'Verbinde Agenten-Netz …',
  'Prüfe Cloud- und Fallback-Gehirne …',
  'Aktiviere Brain-Activity-Stream …',
  'JARVIS bereit.',
];
let bootIdx = 0;
function bootTick() {
  if (bootIdx < BOOT_STEPS.length) {
    bootLines.textContent += (bootIdx ? '\n' : '') + '› ' + BOOT_STEPS[bootIdx];
    bootBar.style.width = Math.round(((bootIdx + 1) / BOOT_STEPS.length) * 100) + '%';
    bootIdx++;
    setTimeout(bootTick, 360);
  } else {
    setTimeout(() => {
      bootEl.classList.add('hide');
      $('hud').classList.add('ready');
      bootDone = true;
      if (!unlocked) showLock();
    }, 500);
  }
}
bootTick();

// ---------- Lock-Screen ----------
let unlocked = false;
let bootDone = false;
let codeBuf = '';
const lockEl = $('lock');
const lockDots = $('lock-dots');
const lockSub = $('lock-sub');

function renderDots() {
  lockDots.innerHTML = '';
  const n = Math.max(codeBuf.length, 4);
  for (let i = 0; i < n; i++) {
    const d = document.createElement('i');
    if (i < codeBuf.length) d.className = 'on';
    lockDots.appendChild(d);
  }
}
function showLock() {
  codeBuf = ''; renderDots();
  lockSub.textContent = 'GESPERRT — CODE EINGEBEN';
  lockEl.classList.remove('hide');
}
function hideLock() { lockEl.classList.add('hide'); }
renderDots();

$('lock-pad').addEventListener('click', (e) => {
  const k = e.target?.dataset?.k;
  if (!k) return;
  if (k === 'clear') { codeBuf = ''; renderDots(); return; }
  if (k === 'ok') {
    if (codeBuf) sendUnlock(codeBuf);
    return;
  }
  if (codeBuf.length < 12) { codeBuf += k; renderDots(); }
});
// Auch echte Tastatur erlauben
window.addEventListener('keydown', (e) => {
  if (lockEl.classList.contains('hide')) return;
  if (e.key >= '0' && e.key <= '9' && codeBuf.length < 12) { codeBuf += e.key; renderDots(); }
  else if (e.key === 'Backspace') { codeBuf = codeBuf.slice(0, -1); renderDots(); }
  else if (e.key === 'Enter' && codeBuf) sendUnlock(codeBuf);
});
function sendUnlock(code) {
  lockSub.textContent = 'PRÜFE …';
  send({ type: 'unlock', code });
}

// ---------- Clock + Reticle-Ticks ----------
const clockEl = $('clock');
function tickClock() {
  const d = new Date(); const p = (n) => String(n).padStart(2, '0');
  clockEl.textContent = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
setInterval(tickClock, 1000); tickClock();

(function buildTicks() {
  const g = $('r-ticks'); if (!g) return;
  const SVG = 'http://www.w3.org/2000/svg';
  for (let i = 0; i < 60; i++) {
    const a = (i / 60) * Math.PI * 2;
    const long = i % 5 === 0;
    const r1 = long ? 186 : 190, r2 = 196;
    const ln = document.createElementNS(SVG, 'line');
    ln.setAttribute('x1', 200 + Math.cos(a) * r1);
    ln.setAttribute('y1', 200 + Math.sin(a) * r1);
    ln.setAttribute('x2', 200 + Math.cos(a) * r2);
    ln.setAttribute('y2', 200 + Math.sin(a) * r2);
    g.appendChild(ln);
  }
})();

// ---------- Three.js: Shader-Kugel (dynamisch, fehlertolerant) ----------
async function initOrb() {
  try {
    const THREE = await import('three');
    const { EffectComposer } = await import('three/addons/postprocessing/EffectComposer.js');
    const { RenderPass } = await import('three/addons/postprocessing/RenderPass.js');
    const { UnrealBloomPass } = await import('three/addons/postprocessing/UnrealBloomPass.js');
    // ---------- Three.js: Shader-Kugel ----------
    const canvas = $('orb-canvas');
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    // MacBook Air (lüfterlos): Pixelratio begrenzen spart viel GPU.
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setClearColor(0x000000, 0);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0, 4.4);

    // Klassische Ashima simplex-noise (snoise) – bewährt, stabil.
    const SNOISE = `
    vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
    vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
    vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
    vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
    float snoise(vec3 v){
      const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
      vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
      vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g;
      vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
      vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
      i=mod289(i);
      vec4 p=permute(permute(permute(
          i.z+vec4(0.0,i1.z,i2.z,1.0))
        + i.y+vec4(0.0,i1.y,i2.y,1.0))
        + i.x+vec4(0.0,i1.x,i2.x,1.0));
      float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
      vec4 j=p-49.0*floor(p*ns.z*ns.z);
      vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
      vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
      vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
      vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
      vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
      vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y);
      vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
      vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
      p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
      vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
      m=m*m; return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
    }`;

    const coreUniforms = {
      uTime:  { value: 0 },
      uAmp:   { value: 0.10 },
      uFreq:  { value: 1.6 },
      uColor: { value: new THREE.Color(0x3a2a8c) },
      uAccent:{ value: new THREE.Color(0x6a4ad8) },
    };
    const coreMat = new THREE.ShaderMaterial({
      uniforms: coreUniforms,
      vertexShader: `
        ${SNOISE}
        uniform float uTime; uniform float uAmp; uniform float uFreq;
        varying float vN; varying vec3 vNormalW; varying vec3 vViewDir;
        void main(){
          float n = snoise(normal*uFreq + uTime*0.35);
          vN = n;
          vec3 displaced = position + normal * n * uAmp;
          vec4 mv = modelViewMatrix * vec4(displaced,1.0);
          vNormalW = normalize(normalMatrix * normal);
          vViewDir = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        uniform vec3 uColor; uniform vec3 uAccent;
        varying float vN; varying vec3 vNormalW; varying vec3 vViewDir;
        void main(){
          float fres = pow(1.0 - max(dot(vViewDir, vNormalW), 0.0), 2.2);
          vec3 base = mix(uColor, uAccent, smoothstep(-0.4, 0.6, vN));
          vec3 col = base + uAccent * fres * 1.4;
          gl_FragColor = vec4(col, 0.92);
        }`,
    });
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(1.0, 12), coreMat);
    scene.add(core);

    const wire = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.28, 3),
      new THREE.MeshBasicMaterial({ color: 0x9b8aff, wireframe: true,
        transparent: true, opacity: 0.30 }),
    );
    scene.add(wire);

    // Fresnel-Glow-Hülle (Backside)
    const glowUniforms = {
      uColor: { value: new THREE.Color(0x4a3acf) },
      uTime:  { value: 0 },
    };
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(1.7, 48, 48),
      new THREE.ShaderMaterial({
        uniforms: glowUniforms, transparent: true, side: THREE.BackSide,
        blending: THREE.AdditiveBlending, depthWrite: false,
        vertexShader: `varying vec3 vN; varying vec3 vV;
          void main(){ vec4 mv=modelViewMatrix*vec4(position,1.0);
            vN=normalize(normalMatrix*normal); vV=normalize(-mv.xyz);
            gl_Position=projectionMatrix*mv; }`,
        fragmentShader: `uniform vec3 uColor; varying vec3 vN; varying vec3 vV;
          void main(){ float i=pow(1.0-max(dot(vV,vN),0.0),3.0);
            gl_FragColor=vec4(uColor, i*0.6); }`,
      }),
    );
    scene.add(glow);

    // Partikel-Schwarm
    const PCOUNT = 220;
    const pPos = new Float32Array(PCOUNT * 3);
    for (let i = 0; i < PCOUNT; i++) {
      const r = 2.0 + Math.random() * 1.6;
      const t = Math.random() * Math.PI * 2;
      const ph = Math.acos(2 * Math.random() - 1);
      pPos[i*3] = r*Math.sin(ph)*Math.cos(t);
      pPos[i*3+1] = r*Math.sin(ph)*Math.sin(t);
      pPos[i*3+2] = r*Math.cos(ph);
    }
    const pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    const particles = new THREE.Points(pGeo, new THREE.PointsMaterial({
      color: 0x9bf0ff, size: 0.022, transparent: true, opacity: 0.6,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    scene.add(particles);

    // Post-Processing (Bloom). Fällt bei Fehler auf direktes Rendering zurück.
    let composer = null, bloom = null;
    try {
      composer = new EffectComposer(renderer);
      composer.addPass(new RenderPass(scene, camera));
      bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.9, 0.65, 0.0);
      composer.addPass(bloom);
    } catch (e) { composer = null; }

    // Arc-Reactor-Palette: Cyan-Kern + Gold-Energie (Iron Man / Batman)
    const STATES = {
      sleeping:  { color:0x0b2740, accent:0xffc14d, amp:0.06, freq:1.2, rot:0.05, bloom:0.5 },
      listening: { color:0x1f9fe0, accent:0x8fe8ff, amp:0.14, freq:1.8, rot:0.22, bloom:1.0 },
      thinking:  { color:0x36c8ff, accent:0xffc14d, amp:0.22, freq:2.8, rot:0.95, bloom:1.25 },
      speaking:  { color:0x7fe4ff, accent:0xffdc92, amp:0.27, freq:3.4, rot:0.4,  bloom:1.6  },
      error:     { color:0xff2d2d, accent:0xff8a3d, amp:0.10, freq:5.0, rot:0.15, bloom:1.1  },
      success:   { color:0x2fd8a0, accent:0xffc14d, amp:0.10, freq:1.6, rot:0.2,  bloom:1.05 },
    };
    let target = STATES.sleeping;
    let speechBoost = 0, speechUntil = 0;
    const anim = {
      color:new THREE.Color(target.color), accent:new THREE.Color(target.accent),
      amp:target.amp, freq:target.freq, rot:target.rot, bloom:target.bloom,
    };
    function applyState(name){ if (STATES[name]) target = STATES[name]; }

    function resizeOrb() {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h; camera.updateProjectionMatrix();
      if (composer) composer.setSize(w, h);
      if (bloom) bloom.setSize(w, h);
    }
    new ResizeObserver(resizeOrb).observe(canvas);
    resizeOrb();

    const clock = new THREE.Clock();
    function frame() {
      const dt = clock.getDelta(), t = clock.getElapsedTime();
      const k = Math.min(1, dt * 8);
      if (Date.now() > speechUntil) speechBoost = Math.max(0, speechBoost - dt * 0.9);

      anim.color.lerp(new THREE.Color(target.color), k);
      anim.accent.lerp(new THREE.Color(target.accent), k);
      anim.amp  += (target.amp  - anim.amp)  * k;
      anim.freq += (target.freq - anim.freq) * k;
      anim.rot  += (target.rot  - anim.rot)  * k;
      anim.bloom += (target.bloom - anim.bloom) * k;

      const pulse = 1 + Math.sin(t * 2.0) * 0.015;
      coreUniforms.uTime.value = t;
      coreUniforms.uAmp.value = (anim.amp + speechBoost * 0.22) * pulse;
      coreUniforms.uFreq.value = anim.freq;
      coreUniforms.uColor.value.copy(anim.color);
      coreUniforms.uAccent.value.copy(anim.accent);
      glowUniforms.uColor.value.copy(anim.color);

      core.rotation.y += anim.rot * dt * 0.5;
      wire.rotation.y -= anim.rot * dt * 0.8;
      wire.rotation.x += anim.rot * dt * 0.3;
      wire.material.color.copy(anim.accent);
      particles.rotation.y += dt * 0.05;
      particles.rotation.x += dt * 0.02;
      particles.material.color.copy(anim.accent);

      if (bloom) bloom.strength = anim.bloom + speechBoost * 0.6;
      if (composer) composer.render(); else renderer.render(scene, camera);
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    function startSpeechImpl(text){ const est=Math.max(900,Math.min((text||"").length*70,30000)); speechBoost=1.0; speechUntil=Date.now()+est; }
    function stopSpeechImpl(){ speechBoost=0; speechUntil=0; }
    orb.setState = applyState;
    orb.startSpeech = startSpeechImpl;
    orb.stopSpeech = stopSpeechImpl;
  } catch (e) { console.warn('[Orb] 3D-Kugel deaktiviert:', e); }
}
initOrb();

// ---------- Sparklines ----------
function makeSpark(id) {
  const c = $(id); if (!c) return { push() {} };
  const ctx = c.getContext('2d'); const data = [];
  return {
    push(v) {
      data.push(Math.max(0, Math.min(100, v)));
      if (data.length > 60) data.shift();
      const W = c.width, H = c.height;
      ctx.clearRect(0, 0, W, H);
      ctx.beginPath();
      data.forEach((d, i) => {
        const x = (i / 59) * W, y = H - (d / 100) * (H - 4) - 2;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      const grad = ctx.createLinearGradient(0, 0, W, 0);
      grad.addColorStop(0, '#45b6ff'); grad.addColorStop(1, '#9bf0ff');
      ctx.strokeStyle = grad; ctx.lineWidth = 1.6; ctx.stroke();
      ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath();
      ctx.fillStyle = 'rgba(69,182,255,0.10)'; ctx.fill();
    },
  };
}
const cpuSpark = makeSpark('cpu-spark');
const ramSpark = makeSpark('ram-spark');

// ---------- Count-up ----------
function countUp(el, toText) {
  const m = String(toText).match(/(\d+(?:\.\d+)?)/);
  if (!m) { el.textContent = toText; return; }
  const to = parseFloat(m[1]); const suffix = String(toText).slice(m.index + m[1].length);
  const prefix = String(toText).slice(0, m.index);
  const from = parseFloat((el.dataset.v || '0')); el.dataset.v = to;
  const t0 = performance.now(); const dur = 500;
  function step(now) {
    const p = Math.min(1, (now - t0) / dur);
    const val = from + (to - from) * (1 - Math.pow(1 - p, 3));
    el.textContent = prefix + (Number.isInteger(to) ? Math.round(val) : val.toFixed(1)) + suffix;
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ---------- WebSocket ----------
const STATE_LABELS = { sleeping:'SCHLÄFT', listening:'HÖRT ZU', thinking:'DENKT',
  speaking:'SPRICHT', error:'FEHLER', success:'BEREIT' };
const stateDot=$('state-dot'), stateLabel=$('state-label'), stateMsg=$('state-message');
const messagesEl=$('messages'), composer=$('composer'), chatInput=$('chat-input');
const speakChk=$('speak-checkbox'), taskList=$('task-list'), tasksCount=$('tasks-count');
const addTaskForm=$('add-task-form'), newTaskInput=$('new-task');
const brainFeed=$('brain-feed'), briefingsList=$('briefings-list'), briefingsCount=$('briefings-count');

let ws = null;
function connect() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => { stateLabel.textContent = 'VERBUNDEN';
    const l = $('ro-link'); if (l) l.textContent = 'LINK: OK'; };
  ws.onmessage = (e) => { let d; try { d = JSON.parse(e.data); } catch { return; } route(d); };
  ws.onclose = () => { stateLabel.textContent = 'GETRENNT';
    const l = $('ro-link'); if (l) l.textContent = 'LINK: ––'; setTimeout(connect, 1500); };
  ws.onerror = () => ws.close();
}
function send(p) { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(p)); }

function route(d) {
  switch (d.type) {
    case 'state': onState(d); break;
    case 'chat': onChat(d); break;
    case 'history': onHistory(d); break;
    case 'tasks': onTasks(d); break;
    case 'system': onSystem(d); break;
    case 'brain': onBrain(d); break;
    case 'briefing': onBriefing(d); break;
    case 'activate': onActivate(d); break;
    case 'health': onHealth(d); break;
    case 'weather': onWeather(d); break;
    case 'agents': onAgents(d); break;
    case 'goals': onGoals(d); break;
    case 'stats': onStats(d); break;
    case 'news': onNews(d); break;
    case 'locked': unlocked = false; if (bootDone) showLock(); break;
    case 'unlocked':
      unlocked = true; hideLock(); break;
    case 'unlock_failed':
      codeBuf = ''; renderDots();
      lockSub.textContent = 'FALSCHER CODE';
      lockEl.classList.add('shake');
      setTimeout(() => lockEl.classList.remove('shake'), 450);
      break;
  }
}

function onWeather({ weather }) {
  if (!weather) return;
  const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  set('weather-city', weather.city || '–');
  set('w-icon', weather.icon || '•');
  set('w-temp', (weather.temp ?? '––') + '°');
  set('w-desc', weather.desc || '');
  set('w-feels', (weather.feels ?? '–') + '°');
  set('w-wind', (weather.wind ?? '–') + ' km/h');
  set('w-hum', (weather.humidity ?? '–') + '%');
  if (weather.today) set('w-today',
    `${weather.today.icon} ${weather.today.min}–${weather.today.max}°`);
  if (weather.tomorrow) set('w-tomorrow',
    `${weather.tomorrow.icon} ${weather.tomorrow.min}–${weather.tomorrow.max}°`);
}

function onAgents({ agents }) {
  const el = $('agents-grid'); if (!el) return;
  el.innerHTML = '';
  const now = Date.now();
  for (const a of agents) {
    const li = document.createElement('li');
    const last = a.last_run ? new Date(a.last_run) : null;
    const recent = last && (now - last.getTime()) < 6 * 3600 * 1000;
    li.className = recent ? 'live' : 'idle';
    const dot = document.createElement('span'); dot.className = 'dot';
    const nm = document.createElement('span'); nm.className = 'a-name';
    nm.textContent = a.description || a.name;
    const wn = document.createElement('span'); wn.className = 'a-when';
    wn.textContent = last ? shortT(a.last_run) : (a.scheduled ? 'geplant' : '–');
    li.append(dot, nm, wn);
    el.appendChild(li);
  }
}

function onGoals({ goals }) {
  const el = $('goals-list'); if (!el) return;
  const cnt = $('goals-count'); if (cnt) cnt.textContent = goals.length;
  el.innerHTML = '';
  if (!goals.length) {
    const li = document.createElement('li'); li.className = 'empty';
    li.textContent = 'Keine aktiven Ziele.'; el.appendChild(li); return;
  }
  for (const g of goals) {
    const li = document.createElement('li');
    li.textContent = g.title;
    if (g.detail) {
      const d = document.createElement('span');
      d.className = 'g-detail'; d.textContent = g.detail;
      li.appendChild(d);
    }
    el.appendChild(li);
  }
}

function onStats({ stats }) {
  const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  set('stat-conversations', stats.conversations_today ?? 0);
  set('stat-tasks', stats.tasks_done_today ?? 0);
  set('stat-briefings', stats.briefings_unread ?? 0);
  set('stat-goals', stats.goals_active ?? 0);
  set('stat-uptime', stats.uptime ?? '0h');
}

function onNews({ news }) {
  const el = $('news-ticker'); if (!el) return;
  if (!news || !news.length) return;
  // Inhalt doppeln für nahtlosen Endlos-Lauf
  el.innerHTML = '';
  const items = [...news, ...news];
  for (const n of items) {
    const s = document.createElement('span');
    s.className = 'ticker-item'; s.textContent = n;
    el.appendChild(s);
  }
}

function onState({ state, message }) {
  stateDot.dataset.state = state || '';
  stateLabel.textContent = STATE_LABELS[state] || (state || '').toUpperCase();
  stateMsg.textContent = message || '';
  setOrbState(state);
}
function onHistory({ messages }) {
  messagesEl.innerHTML = '';
  for (const m of messages) addMessage(m, false);
  scrollChat();
}
function onChat(msg) {
  addMessage(msg, msg.role === 'assistant');
  scrollChat();
}
function addMessage({ role, content, ts }, typed) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const body = document.createElement('span');
  div.appendChild(body);
  if (ts) {
    const tsEl = document.createElement('span');
    tsEl.className = 'ts'; tsEl.textContent = fmtTs(ts);
    div.appendChild(tsEl);
  }
  messagesEl.appendChild(div);
  if (typed && content && content.length < 600) {
    let i = 0;
    (function type() {
      body.textContent = content.slice(0, i++);
      scrollChat();
      if (i <= content.length) setTimeout(type, 12);
    })();
  } else {
    body.textContent = content;
  }
}
function scrollChat() { messagesEl.scrollTop = messagesEl.scrollHeight; }

function onTasks({ tasks }) {
  taskList.innerHTML = ''; tasksCount.textContent = tasks.length;
  if (!tasks.length) {
    const li = document.createElement('li'); li.style.opacity = '.5';
    li.textContent = 'Keine offenen Aufgaben.'; taskList.appendChild(li); return;
  }
  for (const t of tasks) {
    const li = document.createElement('li');
    const main = document.createElement('div'); main.textContent = t.title;
    if (t.due_at) {
      const d = document.createElement('span');
      d.className = 'due'; d.textContent = `fällig ${fmtTs(t.due_at)}`;
      main.appendChild(d);
    }
    const btn = document.createElement('button'); btn.textContent = '✓';
    btn.addEventListener('click', () => send({ type:'complete_task', task_id:t.id }));
    li.append(main, btn); taskList.appendChild(li);
  }
}

function onSystem({ stats }) {
  countUp($('cpu'), stats.cpu || '–');
  $('ram').textContent = stats.ram || '–';
  $('disk').textContent = stats.disk || '–';
  $('battery').textContent = stats.battery || '–';
  $('jarvis-uptime').textContent = stats.jarvis_uptime || '–';
  const cpu = parseInt(stats.cpu, 10); if (!isNaN(cpu)) {
    cpuSpark.push(cpu);
    const ro = $('ro-cpu'); if (ro) ro.textContent = `CPU ${cpu}%`;
  }
  const ram = parseInt(stats.ram, 10); if (!isNaN(ram)) ramSpark.push(ram);
}

function onBrain(d) {
  const li = document.createElement('li');
  li.dataset.kind = d.kind || '';
  const ts = document.createElement('span'); ts.className='ts'; ts.textContent=shortT(d.ts);
  const kd = document.createElement('span'); kd.className='kind';
  kd.textContent = (d.kind||'').replace(/_/g,' ');
  const ct = document.createElement('span'); ct.className='content'; ct.textContent=d.content||'';
  li.append(ts, kd, ct);
  brainFeed.appendChild(li);
  while (brainFeed.children.length > 60) brainFeed.firstChild.remove();
  brainFeed.scrollTop = brainFeed.scrollHeight;
  if (d.kind === 'speech_start') startSpeech(d.content || '');
  if (d.kind === 'speech_end') stopSpeech();
}

function onBriefing({ briefing, unread_total }) {
  if (briefing) {
    const li = document.createElement('li');
    const ti = document.createElement('span'); ti.className='title';
    ti.textContent = briefing.title || briefing.agent;
    const ts = document.createElement('span'); ts.className='ts';
    ts.textContent = shortT(new Date().toISOString());
    const ct = document.createElement('div'); ct.className='content';
    ct.textContent = (briefing.content || '').slice(0, 220);
    li.append(ti, ts, ct);
    briefingsList.prepend(li);
    while (briefingsList.children.length > 15) briefingsList.lastChild.remove();
  }
  briefingsCount.textContent = unread_total ?? briefingsList.children.length;
}

function onActivate() {
  window.jarvis?.focus?.();
  document.body.animate(
    [{ boxShadow:'inset 0 0 120px rgba(69,182,255,0.55)' },
     { boxShadow:'inset 0 0 0 rgba(69,182,255,0)' }],
    { duration: 1000, easing: 'ease-out' });
}

function onHealth({ health }) {
  if (!health) return;
  const dot = $('health-dot'), label = $('health-label'), mode = $('ro-mode');
  let st='online', tx='online';
  if (!health.online) { st='offline'; tx='offline'; }
  else if (health.degraded || !health.api_ok) { st='degraded'; tx='eingeschränkt'; }
  dot.dataset.state = st; label.textContent = tx;
  if (mode) mode.textContent = 'MODE: ' + tx.toUpperCase();
}

// ---------- Eingaben ----------
composer.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = chatInput.value.trim(); if (!text) return;
  send({ type:'chat', content:text, speak:speakChk.checked });
  chatInput.value = '';
});
addTaskForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const title = newTaskInput.value.trim(); if (!title) return;
  send({ type:'add_task', title }); newTaskInput.value = '';
});
const QUICK = {
  news:'Was sind die wichtigsten News heute?',
  weather:'Wie wird das Wetter heute und morgen?',
  briefings:'Was ist neu? Lies mir die offenen Briefings vor.',
  status:'Wie ist gerade der Mac-Status?',
  profile:'Was weißt du eigentlich über mich?',
  goals:'Was verfolgst du gerade eigenständig für mich?',
};
document.querySelectorAll('.quick').forEach((b) => {
  b.addEventListener('click', () => {
    const p = QUICK[b.dataset.action];
    if (p) send({ type:'chat', content:p, speak:speakChk.checked });
  });
});

// ---------- Helfer ----------
function fmtTs(iso) {
  try { const d = new Date(iso); if (isNaN(d)) return iso;
    return d.toLocaleString('de-DE', { day:'2-digit', month:'2-digit',
      hour:'2-digit', minute:'2-digit' }); } catch { return iso; }
}
function shortT(iso) {
  try { const d = new Date(iso); if (isNaN(d)) return '';
    const p = (n) => String(n).padStart(2,'0');
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; }
  catch { return ''; }
}

connect();
