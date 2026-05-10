// JARVIS-Dashboard – Live-Verbindung zum Backend via WebSocket.
//
// Empfangene Nachrichten haben ein `type`-Feld und werden an die
// passenden Handler verteilt. Eingaben (Chat, Aufgaben) werden als
// JSON über denselben Socket gesendet.

const WS_URL = 'ws://127.0.0.1:8765';

const $ = (id) => document.getElementById(id);

const stateDot = $('state-dot');
const stateLabel = $('state-label');
const stateMsg = $('state-message');
const messagesEl = $('messages');
const composer = $('composer');
const chatInput = $('chat-input');
const speakChk = $('speak-checkbox');
const cpuEl = $('cpu');
const cpuBar = $('cpu-bar');
const ramEl = $('ram');
const diskEl = $('disk');
const batteryEl = $('battery');
const sysUptimeEl = $('system-uptime');
const jarvisUptimeEl = $('jarvis-uptime');
const taskList = $('task-list');
const addTaskForm = $('add-task-form');
const newTaskInput = $('new-task');
const newTaskDue = $('new-task-due');

const STATE_LABELS = {
  sleeping: 'Schläft',
  listening: 'Hört zu…',
  thinking: 'Denkt…',
  speaking: 'Spricht…',
  error: 'Fehler',
  success: 'Bereit',
};

let ws = null;

function connect() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    stateLabel.textContent = 'Verbunden';
  };
  ws.onmessage = (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    switch (data.type) {
      case 'state':   onState(data); break;
      case 'chat':    onChat(data); break;
      case 'history': onHistory(data); break;
      case 'tasks':   onTasks(data); break;
      case 'system':  onSystem(data); break;
    }
  };
  ws.onclose = () => {
    stateLabel.textContent = 'getrennt';
    stateDot.dataset.state = '';
    setTimeout(connect, 1500);
  };
  ws.onerror = () => ws.close();
}

function send(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

// --- Handler ---

function onState({ state, message }) {
  stateDot.dataset.state = state || '';
  stateLabel.textContent = STATE_LABELS[state] || state || '';
  stateMsg.textContent = message || '';
}

function onHistory({ messages }) {
  messagesEl.innerHTML = '';
  for (const m of messages) addMessage(m);
  scrollChat();
}

function onChat(msg) {
  addMessage(msg);
  scrollChat();
}

function addMessage({ role, content, ts }) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = content;
  if (ts) {
    const tsEl = document.createElement('span');
    tsEl.className = 'ts';
    tsEl.textContent = formatTs(ts);
    div.appendChild(tsEl);
  }
  messagesEl.appendChild(div);
}

function scrollChat() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function onTasks({ tasks }) {
  taskList.innerHTML = '';
  if (!tasks.length) {
    const li = document.createElement('li');
    li.style.opacity = '.5';
    li.textContent = 'Keine offenen Aufgaben.';
    taskList.appendChild(li);
    return;
  }
  for (const t of tasks) {
    const li = document.createElement('li');
    const main = document.createElement('div');
    main.textContent = t.title;
    if (t.due_at) {
      const due = document.createElement('span');
      due.className = 'due';
      due.textContent = `fällig ${formatTs(t.due_at)}`;
      main.appendChild(due);
    }
    const btn = document.createElement('button');
    btn.textContent = '✓';
    btn.title = 'Erledigt';
    btn.addEventListener('click', () => send({ type: 'complete_task', task_id: t.id }));
    li.appendChild(main);
    li.appendChild(btn);
    taskList.appendChild(li);
  }
}

function onSystem({ stats }) {
  cpuEl.textContent = stats.cpu || '–';
  ramEl.textContent = stats.ram || '–';
  diskEl.textContent = stats.disk || '–';
  batteryEl.textContent = stats.battery || '–';
  sysUptimeEl.textContent = stats.system_uptime || '–';
  jarvisUptimeEl.textContent = stats.jarvis_uptime || '–';
  // CPU-Balken
  const pct = parseInt(stats.cpu, 10);
  if (!isNaN(pct)) cpuBar.style.width = Math.min(100, pct) + '%';
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
  const due = newTaskDue.value || null;
  send({ type: 'add_task', title, due_at: due });
  newTaskInput.value = '';
  newTaskDue.value = '';
});

// Schnellaktionen: lösen einfache vordefinierte Anfragen aus.
const QUICK_PROMPTS = {
  news: 'Was sind die wichtigsten News heute?',
  weather: 'Wie wird das Wetter heute und morgen?',
  calendar: 'Öffne bitte die Kalender-App.',
  reminder: null,    // Inline: fokussiert das Aufgaben-Eingabefeld
  settings: null,    // Platzhalter für Phase 7
};

document.querySelectorAll('.quick').forEach((btn) => {
  btn.addEventListener('click', () => {
    const action = btn.dataset.action;
    if (action === 'reminder') { newTaskInput.focus(); return; }
    if (action === 'settings') {
      stateMsg.textContent = 'Einstellungen: folgt in Phase 7.';
      return;
    }
    const prompt = QUICK_PROMPTS[action];
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

connect();
