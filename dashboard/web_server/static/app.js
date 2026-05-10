// JARVIS Mobile Web-Frontend.
// Verbindet sich relativ zur Origin (egal ob localhost oder jarvis.local).

const $ = (id) => document.getElementById(id);

const stateDot = $('state-dot');
const stateLabel = $('state-label');
const stateMsg = $('state-msg');
const messagesEl = $('messages');
const composer = $('composer');
const chatInput = $('chat-input');
const speakChk = $('speak-checkbox');
const taskList = $('task-list');
const addTaskForm = $('add-task-form');
const newTaskInput = $('new-task');
const newTaskDue = $('new-task-due');
const cpuEl = $('cpu');
const ramEl = $('ram');
const diskEl = $('disk');
const batteryEl = $('battery');
const sysUptimeEl = $('system-uptime');
const jarvisUptimeEl = $('jarvis-uptime');

const STATE_LABELS = {
  sleeping: 'Schläft', listening: 'Hört zu…',
  thinking: 'Denkt…', speaking: 'Spricht…',
  error: 'Fehler',    success: 'Bereit',
};

// --- Tab-Steuerung ---
const tabs = document.querySelectorAll('.tabs button');
tabs.forEach((b) => b.addEventListener('click', () => switchTab(b.dataset.tab)));

function switchTab(tab) {
  document.querySelectorAll('.tab-content').forEach((s) => {
    s.classList.toggle('hidden', s.dataset.tab !== tab);
  });
  tabs.forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  composer.classList.toggle('hidden', tab !== 'chat');
}

// --- WebSocket-Verbindung ---
let ws = null;
function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/ws`;
}

function connect() {
  ws = new WebSocket(wsUrl());
  ws.onopen = () => { stateLabel.textContent = 'Verbunden'; };
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
  messages.forEach(addMessage);
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
    li.style.opacity = '.55';
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
    btn.textContent = 'Erledigt';
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
  sysUptimeEl.textContent = stats.system_uptime || '–';
  jarvisUptimeEl.textContent = stats.jarvis_uptime || '–';
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
