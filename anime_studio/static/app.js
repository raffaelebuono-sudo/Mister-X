"use strict";

// ---------------------------------------------------------------------------
// Zustand
// ---------------------------------------------------------------------------
const state = {
  series: null,        // aktuell geoeffnete Serie
  episodeIndex: 0,     // welche Folge im Player
  sceneIndex: 0,       // welche Szene
  lineIndex: 0,        // welche Dialogzeile
  autoplay: false,
  autoTimer: null,
  typing: null,
  imagesEnabled: false, // ist ein Bild-Key gesetzt?
  voicesEnabled: false, // ElevenLabs verfuegbar?
  videoEnabled: false,  // ffmpeg/Video-Export verfuegbar?
  audioEl: null,        // laufende Server-Audiowiedergabe
};

// Zeichenstil-Voreinstellungen (leer = Server-Standard: One-Piece-Look)
const STYLE_PRESETS = [
  { label: "Shonen-Piraten-Abenteuer (One-Piece-Look)", value: "" },
  { label: "Modern & hochglanz (Action-Look)",
    value: "modern high-budget anime style, ultra detailed, cinematic dramatic lighting, vibrant saturated colors, sharp cel shading, dynamic action" },
  { label: "Sanft & malerisch (Ghibli-artig)",
    value: "soft painterly anime style, warm gentle colors, lush hand-painted backgrounds, whimsical cozy atmosphere, watercolor feel" },
  { label: "Retro 90er-Anime",
    value: "retro 1990s anime style, slight film grain, muted nostalgic colors, classic hand-drawn cel animation look" },
  { label: "Dunkel & ernst (Seinen)",
    value: "dark gritty seinen anime style, dramatic deep shadows, moody atmosphere, detailed semi-realistic proportions" },
];

const $ = (id) => document.getElementById(id);
const api = async (url, opts = {}) => {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Fehler");
  }
  return res.json();
};

// Farbe aus Namen ableiten (stabile, huebsche Avatar-Farbe)
function colorFor(name) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `hsl(${h}, 65%, 55%)`;
}
function initialOf(name) {
  const t = (name || "?").trim();
  return t ? t[0].toUpperCase() : "?";
}

// ---------------------------------------------------------------------------
// Ansichten wechseln
// ---------------------------------------------------------------------------
function showHome() {
  stopAutoplay();
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $("view-home").classList.add("active");
  loadSeriesList();
}
function showSeries() {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $("view-series").classList.add("active");
}
window.showHome = showHome;

// ---------------------------------------------------------------------------
// Startseite
// ---------------------------------------------------------------------------
async function loadStatus() {
  try {
    const s = await api("/api/status");
    state.imagesEnabled = !!s.images_enabled;
    state.voicesEnabled = !!s.voices_enabled;
    state.videoEnabled = !!s.video_enabled;
    state.clipsEnabled = !!s.clips_enabled;
    state.musicEnabled = !!s.music_enabled;
    state.loraEnabled = !!s.lora_enabled;
    // Export-Optionen nur zeigen, wenn verfuegbar
    const opts = $("exportOpts");
    if (opts && (state.clipsEnabled || state.musicEnabled)) {
      opts.style.display = "flex";
      $("optClips").disabled = !state.clipsEnabled;
      $("optMusic").disabled = !state.musicEnabled;
      $("optHint").textContent = "(KI-Clips dauern und kosten extra)";
    }
    const badge = $("modeBadge");
    const img = s.images_enabled ? " · 🎨 " + s.image_provider : " · 🎨 aus";
    if (s.demo_mode) {
      badge.textContent = "Demo-Modus (kein Story-Key)" + img;
      badge.classList.add("demo");
    } else {
      badge.textContent = "KI aktiv · " + s.model + img;
    }
  } catch {
    $("modeBadge").textContent = "offline";
  }
}

function fillStylePresets() {
  const sel = $("newStyle");
  if (!sel) return;
  sel.innerHTML = "";
  STYLE_PRESETS.forEach((p, i) => {
    const o = document.createElement("option");
    o.value = String(i);
    o.textContent = p.label;
    sel.appendChild(o);
  });
}

async function loadSeriesList() {
  const ul = $("seriesList");
  try {
    const list = await api("/api/series");
    if (!list.length) {
      ul.innerHTML = '<li class="muted">Noch keine Serie. Erstelle deine erste!</li>';
      return;
    }
    ul.innerHTML = "";
    for (const s of list) {
      const li = document.createElement("li");
      li.innerHTML = `
        <div>
          <div><strong>${escapeHtml(s.title)}</strong></div>
          <div class="meta">${escapeHtml(s.genre)} · ${s.episode_count} Folge(n)</div>
        </div>
        <div>
          <button class="open">Öffnen</button>
          <button class="del" title="Löschen">🗑</button>
        </div>`;
      li.querySelector(".open").onclick = () => openSeries(s.id);
      li.querySelector(".del").onclick = () => deleteSeries(s.id, s.title);
      ul.appendChild(li);
    }
  } catch (e) {
    ul.innerHTML = `<li class="muted">Fehler: ${escapeHtml(e.message)}</li>`;
  }
}

$("btnCreate").onclick = async () => {
  const title = $("newTitle").value.trim();
  if (!title) { $("newTitle").focus(); return; }
  const characters = $("newChars").value
    .split(",").map((s) => s.trim()).filter(Boolean)
    .map((name) => ({ name, role: "Hauptcharakter" }));
  const styleIdx = parseInt($("newStyle").value || "0", 10);
  const art_style = (STYLE_PRESETS[styleIdx] || STYLE_PRESETS[0]).value;
  try {
    const series = await api("/api/series", {
      method: "POST",
      body: JSON.stringify({
        title,
        genre: $("newGenre").value.trim() || "Abenteuer",
        characters,
        art_style,
      }),
    });
    $("newTitle").value = $("newGenre").value = $("newChars").value = "";
    openSeriesData(series);
  } catch (e) {
    alert("Konnte Serie nicht erstellen: " + e.message);
  }
};

async function deleteSeries(id, title) {
  if (!confirm(`Serie „${title}" wirklich löschen?`)) return;
  await api(`/api/series/${id}`, { method: "DELETE" });
  loadSeriesList();
}

// ---------------------------------------------------------------------------
// Serienansicht
// ---------------------------------------------------------------------------
async function openSeries(id) {
  const series = await api(`/api/series/${id}`);
  openSeriesData(series);
}

function openSeriesData(series) {
  state.series = series;
  $("seriesTitle").textContent = series.title;
  $("seriesGenre").textContent = series.genre;
  renderEpisodeList();
  renderLoraPanel();
  showSeries();
  if (series.episodes.length) {
    playEpisode(series.episodes.length - 1);
  } else {
    $("player").classList.add("hidden");
    $("emptyStage").classList.remove("hidden");
  }
  $("epKeywords").focus();
}

const LORA_LABEL = {
  none: "nicht trainiert",
  training: "⏳ trainiert…",
  ready: "✅ konsistent",
  failed: "⚠️ fehlgeschlagen",
};

function renderLoraPanel() {
  const panel = $("loraPanel");
  if (!panel || !state.loraEnabled) { if (panel) panel.style.display = "none"; return; }
  const chars = state.series.characters || [];
  if (!chars.length) { panel.style.display = "none"; return; }
  panel.style.display = "block";
  const ul = $("loraList");
  ul.innerHTML = "";
  chars.forEach((c) => {
    const st = (c.lora && c.lora.status) || "none";
    const li = document.createElement("li");
    li.className = "lora-item";
    const label = document.createElement("span");
    label.innerHTML = `<b>${c.name}</b> <span class="muted small">${LORA_LABEL[st] || st}</span>`;
    li.appendChild(label);
    if (st === "none" || st === "failed") {
      const btn = document.createElement("button");
      btn.className = "ghost small";
      btn.textContent = "trainieren";
      btn.onclick = () => trainLora(c.name);
      li.appendChild(btn);
    } else if (st === "training") {
      pollLora(c.name); // automatisch weiter abfragen
    }
    ul.appendChild(li);
  });
}

async function trainLora(name) {
  if (!confirm(`LoRA-Training für „${name}" starten?\nDas dauert ~10–20 Min und kostet GPU-Zeit auf deinem Replicate-Account.`))
    return;
  try {
    await api(`/api/series/${state.series.id}/character/${encodeURIComponent(name)}/train-lora`,
      { method: "POST" });
    const c = state.series.characters.find((x) => x.name === name);
    if (c) c.lora = { status: "training" };
    renderLoraPanel();
  } catch (e) {
    alert("Training-Fehler: " + e.message);
  }
}

async function pollLora(name) {
  if (state._loraPolling && state._loraPolling[name]) return;
  state._loraPolling = state._loraPolling || {};
  state._loraPolling[name] = true;
  setTimeout(async () => {
    try {
      const res = await api(
        `/api/series/${state.series.id}/character/${encodeURIComponent(name)}/lora`);
      const c = state.series.characters.find((x) => x.name === name);
      if (c) c.lora = res.lora;
    } catch (_) { /* still pollen */ }
    state._loraPolling[name] = false;
    renderLoraPanel();
  }, 20000); // alle 20 s
}

function renderEpisodeList() {
  const ul = $("episodeList");
  ul.innerHTML = "";
  state.series.episodes.forEach((ep, i) => {
    const li = document.createElement("li");
    if (i === state.episodeIndex) li.classList.add("active");
    li.innerHTML = `<span class="num">F${ep.number}</span>${escapeHtml(ep.episode_title)}`;
    li.onclick = () => playEpisode(i);
    ul.appendChild(li);
  });
  if (!state.series.episodes.length) {
    ul.innerHTML = '<li class="muted small">Noch keine Folgen.</li>';
  }
}

$("btnGenerate").onclick = async () => {
  const keywords = $("epKeywords").value.trim();
  if (!keywords) { $("epKeywords").focus(); return; }
  $("btnGenerate").disabled = true;
  $("genHint").textContent = "";
  $("player").classList.add("hidden");
  $("emptyStage").classList.add("hidden");
  $("loader").classList.remove("hidden");
  try {
    const res = await api(`/api/series/${state.series.id}/episode`, {
      method: "POST",
      body: JSON.stringify({ keywords }),
    });
    state.series = res.series;
    $("epKeywords").value = "";
    renderEpisodeList();
    const newEp = state.series.episodes[state.series.episodes.length - 1];
    playEpisode(state.series.episodes.length - 1);
    // Bilder automatisch erzeugen (falls Bild-Key vorhanden)
    if (state.imagesEnabled) generateAllImages(newEp.number);
  } catch (e) {
    $("genHint").textContent = "Fehler: " + e.message;
    $("emptyStage").classList.remove("hidden");
  } finally {
    $("loader").classList.add("hidden");
    $("btnGenerate").disabled = false;
  }
};

// ---------------------------------------------------------------------------
// Player
// ---------------------------------------------------------------------------
function playEpisode(index) {
  stopAutoplay();
  state.episodeIndex = index;
  state.sceneIndex = 0;
  state.lineIndex = 0;
  $("emptyStage").classList.add("hidden");
  $("loader").classList.add("hidden");
  $("player").classList.remove("hidden");
  renderEpisodeList();
  renderScene();
}

function currentEpisode() { return state.series.episodes[state.episodeIndex]; }

function renderScene() {
  const ep = currentEpisode();
  const scene = ep.scenes[state.sceneIndex];
  if (!scene) return;

  // Hintergrund nach Stimmung (Fallback hinter dem Bild)
  const bg = $("sceneBg");
  bg.className = "scene-bg mood-" + (scene.mood || "ruhig");

  // Szenenbild (falls vorhanden)
  const img = $("sceneImg");
  const shade = $("sceneShade");
  if (scene.image) {
    img.src = scene.image;
    img.classList.remove("hidden");
    shade.classList.remove("hidden");
    // Ken-Burns-Animation neu starten
    img.classList.remove("kb");
    void img.offsetWidth; // Reflow erzwingen
    img.classList.add("kb");
  } else {
    img.classList.add("hidden");
    shade.classList.add("hidden");
  }

  $("sceneLocation").textContent = "📍 " + scene.location;
  $("narration").textContent = scene.narration || "";

  renderLine();
  updateProgress();

  $("epMeta").innerHTML =
    `<div><strong>Folge ${ep.number}: ${escapeHtml(ep.episode_title)}</strong></div>` +
    `<div>${escapeHtml(ep.synopsis || "")}</div>` +
    (state.sceneIndex === ep.scenes.length - 1 && ep.cliffhanger
      ? `<div class="cliff">▶ ${escapeHtml(ep.cliffhanger)}</div>` : "");
}

function renderLine() {
  const scene = currentEpisode().scenes[state.sceneIndex];
  const line = scene.dialogue[state.lineIndex];
  const avatar = $("charAvatar");
  const nameEl = $("charName");

  if (!line) {
    avatar.style.display = "none";
    nameEl.textContent = "";
    $("dlgSpeaker").textContent = "";
    $("dlgText").textContent = "…";
    return;
  }

  const hasImage = !!scene.image;
  avatar.style.display = hasImage ? "none" : "flex";
  nameEl.style.display = hasImage ? "none" : "block";
  avatar.textContent = initialOf(line.speaker);
  avatar.style.background = colorFor(line.speaker);
  avatar.style.transform = "scale(1)";
  // kleiner "Pop"-Effekt beim Sprecherwechsel
  requestAnimationFrame(() => { avatar.style.transform = "scale(1.06)"; });
  nameEl.textContent = line.speaker;

  const emo = line.emotion ? ` (${line.emotion})` : "";
  $("dlgSpeaker").textContent = line.speaker + emo;
  typeText($("dlgText"), line.text);
  if (typeof voice !== "undefined" && voice.on) speakLine(line);
}

// Schreibmaschinen-Effekt
function typeText(el, text) {
  clearInterval(state.typing);
  el.textContent = "";
  let i = 0;
  state.typing = setInterval(() => {
    el.textContent = text.slice(0, ++i);
    if (i >= text.length) clearInterval(state.typing);
  }, 22);
}

function updateProgress() {
  const ep = currentEpisode();
  $("progress").textContent =
    `Szene ${state.sceneIndex + 1}/${ep.scenes.length}`;
}

function advance(dir) {
  const ep = currentEpisode();
  const scene = ep.scenes[state.sceneIndex];
  // Wenn noch Text tippt -> erst Text vervollstaendigen
  if (dir > 0 && state.typing) {
    clearInterval(state.typing);
    const line = scene.dialogue[state.lineIndex];
    if (line) { $("dlgText").textContent = line.text; state.typing = null; return; }
  }

  let li = state.lineIndex + dir;
  let si = state.sceneIndex;
  if (li >= scene.dialogue.length) {        // naechste Szene
    si += 1; li = 0;
  } else if (li < 0) {                       // vorherige Szene
    si -= 1;
    li = si >= 0 ? ep.scenes[si].dialogue.length - 1 : 0;
  }

  if (si < 0) return;                        // Anfang
  if (si >= ep.scenes.length) {              // Ende der Folge
    stopAutoplay();
    return;
  }
  state.sceneIndex = si;
  state.lineIndex = Math.max(0, li);
  renderScene();
}

$("btnNext").onclick = () => advance(1);
$("btnPrev").onclick = () => advance(-1);

function startAutoplay() {
  state.autoplay = true;
  $("btnAuto").textContent = "⏸ Pause";
  state.autoTimer = setInterval(() => {
    const ep = currentEpisode();
    const atEnd =
      state.sceneIndex === ep.scenes.length - 1 &&
      state.lineIndex === ep.scenes[state.sceneIndex].dialogue.length - 1;
    if (atEnd && !state.typing) { stopAutoplay(); return; }
    advance(1);
  }, 2600);
}
function stopAutoplay() {
  state.autoplay = false;
  clearInterval(state.autoTimer);
  $("btnAuto").textContent = "▶ Autoplay";
  if (typeof stopAudio === "function") stopAudio();
}
$("btnAuto").onclick = () => (state.autoplay ? stopAutoplay() : startAutoplay());

// Tastatursteuerung
document.addEventListener("keydown", (e) => {
  if (!$("view-series").classList.contains("active")) return;
  if (document.activeElement.tagName === "TEXTAREA") return;
  if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); advance(1); }
  if (e.key === "ArrowLeft") advance(-1);
});

// ---------------------------------------------------------------------------
// Stimmen (Sprachausgabe per Browser – kein Key noetig)
// ---------------------------------------------------------------------------
const voice = { on: false, deVoices: [] };

function loadVoices() {
  const all = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  voice.deVoices = all.filter((v) => v.lang && v.lang.toLowerCase().startsWith("de"));
}
if (window.speechSynthesis) {
  loadVoices();
  speechSynthesis.onvoiceschanged = loadVoices;
}

// Pro Charakter eine stabile Stimme + Tonhoehe ableiten
function voiceForSpeaker(name) {
  const pool = voice.deVoices.length ? voice.deVoices : speechSynthesis.getVoices();
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 100000;
  const v = pool.length ? pool[h % pool.length] : null;
  const pitch = 0.7 + ((h % 70) / 100);   // 0.7 – 1.4
  const rate = 0.9 + ((h % 25) / 100);    // 0.9 – 1.15
  return { v, pitch, rate };
}

function stopAudio() {
  if (window.speechSynthesis) speechSynthesis.cancel();
  if (state.audioEl) { state.audioEl.pause(); state.audioEl = null; }
}

// Browser-Sprachausgabe (gratis, kein Key)
function browserSpeak(line) {
  if (!window.speechSynthesis || !line || !line.text) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(line.text);
  const cfg = voiceForSpeaker(line.speaker || "?");
  if (cfg.v) u.voice = cfg.v;
  u.lang = "de-DE";
  u.pitch = cfg.pitch;
  u.rate = cfg.rate;
  speechSynthesis.speak(u);
}

// Spielt die aktuelle Zeile: ElevenLabs (falls Key) sonst Browser-Stimme
async function speakLine(line) {
  if (!line || !line.text) return;
  stopAudio();
  if (state.voicesEnabled) {
    try {
      let url = line.audio;
      if (!url) {
        const res = await api(
          `/api/series/${state.series.id}/episode/${currentEpisode().number}/line-audio`,
          { method: "POST", body: JSON.stringify(
              { scene_index: state.sceneIndex, hint: String(state.lineIndex) }) }
        );
        url = res.audio;
        line.audio = url;
      }
      state.audioEl = new Audio(url);
      state.audioEl.play().catch(() => browserSpeak(line));
      return;
    } catch (e) {
      // Fallback auf Browser-Stimme
    }
  }
  browserSpeak(line);
}

function currentLine() {
  const sc = currentEpisode().scenes[state.sceneIndex];
  return sc ? sc.dialogue[state.lineIndex] : null;
}

$("btnVoice").onclick = () => {
  voice.on = !voice.on;
  $("btnVoice").textContent = "🔊 Stimmen: " + (voice.on ? "an" : "aus");
  if (!voice.on) stopAudio();
  if (voice.on) speakLine(currentLine());
};
$("btnSpeak").onclick = () => speakLine(currentLine());

// ---------------------------------------------------------------------------
// Szene neu generieren (KI)
// ---------------------------------------------------------------------------
$("btnRegen").onclick = async () => {
  const hint = prompt(
    "Optionaler Hinweis, wie die Szene anders werden soll (leer = einfach neu):",
    ""
  );
  if (hint === null) return; // abgebrochen
  const ep = currentEpisode();
  $("btnRegen").disabled = true;
  $("btnRegen").textContent = "🎲 …";
  try {
    const res = await api(
      `/api/series/${state.series.id}/episode/${ep.number}/regen-scene`,
      {
        method: "POST",
        body: JSON.stringify({ scene_index: state.sceneIndex, hint: hint || "" }),
      }
    );
    state.series = res.series;
    state.lineIndex = 0;
    renderScene();
  } catch (e) {
    alert("Fehler: " + e.message);
  } finally {
    $("btnRegen").disabled = false;
    $("btnRegen").textContent = "🎲 Szene neu";
  }
};

// ---------------------------------------------------------------------------
// Bild fuer Szene generieren (KI)
// ---------------------------------------------------------------------------
async function generateImage(epNumber, sceneIndex) {
  const res = await api(
    `/api/series/${state.series.id}/episode/${epNumber}/scene-image`,
    { method: "POST", body: JSON.stringify({ scene_index: sceneIndex, hint: "" }) }
  );
  // Bild in den lokalen Zustand uebernehmen
  const ep = state.series.episodes.find((e) => e.number === epNumber);
  if (ep && ep.scenes[sceneIndex]) ep.scenes[sceneIndex].image = res.image;
  return res.image;
}

$("btnImage").onclick = async () => {
  if (!state.imagesEnabled) {
    alert("Kein Bild-Key gesetzt. Trage OPENAI_API_KEY oder GEMINI_API_KEY in die .env ein.");
    return;
  }
  const ep = currentEpisode();
  const btn = $("btnImage");
  btn.disabled = true; btn.textContent = "🎨 zeichnet…";
  try {
    await generateImage(ep.number, state.sceneIndex);
    renderScene();
  } catch (e) {
    alert("Bild-Fehler: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "🎨 Bild für Szene";
  }
};

// Alle Szenenbilder einer Folge nacheinander erzeugen (mit Fortschritt)
async function generateAllImages(epNumber) {
  if (!state.imagesEnabled) return;
  const ep = state.series.episodes.find((e) => e.number === epNumber);
  if (!ep) return;
  const hint = $("genHint");
  for (let i = 0; i < ep.scenes.length; i++) {
    if (ep.scenes[i].image) continue;
    hint.textContent = `🎨 Zeichne Bild ${i + 1}/${ep.scenes.length}…`;
    try {
      await generateImage(epNumber, i);
      if (state.episodeIndex === state.series.episodes.indexOf(ep) &&
          state.sceneIndex === i) renderScene();
    } catch (e) {
      hint.textContent = "Bild-Fehler: " + e.message;
      return;
    }
  }
  hint.textContent = "✓ Bilder fertig.";
  renderScene();
}

// ---------------------------------------------------------------------------
// Video-Export (MP4)
// ---------------------------------------------------------------------------
$("btnExport").onclick = async () => {
  if (!state.videoEnabled) {
    alert("Video-Export ist auf diesem Server nicht verfügbar (ffmpeg fehlt).");
    return;
  }
  const ep = currentEpisode();
  const useClips = !!($("optClips") && $("optClips").checked);
  const useMusic = !!($("optMusic") && $("optMusic").checked);
  const btn = $("btnExport");
  btn.disabled = true;
  btn.textContent = useClips ? "🎞️ rendert KI-Clips… (dauert)" : "🎞️ rendert…";
  try {
    const res = await api(
      `/api/series/${state.series.id}/episode/${ep.number}/export`,
      { method: "POST", body: JSON.stringify({ use_clips: useClips, use_music: useMusic }) }
    );
    ep.video = res.video;
    $("videoPlayer").src = res.video;
    $("videoDownload").href = res.video;
    $("videoOverlay").classList.remove("hidden");
  } catch (e) {
    alert("Video-Fehler: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "🎞️ Als Video exportieren";
  }
};
$("videoClose").onclick = () => {
  $("videoPlayer").pause();
  $("videoOverlay").classList.add("hidden");
};

// ---------------------------------------------------------------------------
// Szenen-Editor
// ---------------------------------------------------------------------------
function openEditor() {
  const scene = currentEpisode().scenes[state.sceneIndex];
  $("edLocation").value = scene.location || "";
  $("edMood").value = scene.mood || "ruhig";
  $("edNarration").value = scene.narration || "";
  $("edDialogue").innerHTML = "";
  (scene.dialogue || []).forEach((line) => addDialogueRow(line));
  if (!scene.dialogue || !scene.dialogue.length) addDialogueRow();
  $("editorOverlay").classList.remove("hidden");
}

function addDialogueRow(line = { speaker: "", emotion: "", text: "" }) {
  const row = document.createElement("div");
  row.className = "ed-row";
  row.innerHTML = `
    <input class="ed-speaker" placeholder="Sprecher" value="${escapeAttr(line.speaker)}" />
    <input class="ed-emotion" placeholder="Gefühl" value="${escapeAttr(line.emotion)}" />
    <input class="ed-text" placeholder="Text" value="${escapeAttr(line.text)}" />
    <button class="ed-del" title="Zeile löschen">✕</button>`;
  row.querySelector(".ed-del").onclick = () => row.remove();
  $("edDialogue").appendChild(row);
}

$("edAddLine").onclick = () => addDialogueRow();
$("edCancel").onclick = () => $("editorOverlay").classList.add("hidden");
$("btnEdit").onclick = openEditor;

$("edSave").onclick = async () => {
  const ep = JSON.parse(JSON.stringify(currentEpisode())); // Kopie
  const scene = ep.scenes[state.sceneIndex];
  scene.location = $("edLocation").value.trim();
  scene.mood = $("edMood").value;
  scene.narration = $("edNarration").value.trim();
  scene.dialogue = [...document.querySelectorAll("#edDialogue .ed-row")]
    .map((r) => ({
      speaker: r.querySelector(".ed-speaker").value.trim() || "???",
      emotion: r.querySelector(".ed-emotion").value.trim(),
      text: r.querySelector(".ed-text").value.trim(),
    }))
    .filter((l) => l.text);
  try {
    const res = await api(
      `/api/series/${state.series.id}/episode/${ep.number}`,
      { method: "PUT", body: JSON.stringify({ episode: ep }) }
    );
    state.series = res.series;
    $("editorOverlay").classList.add("hidden");
    state.lineIndex = 0;
    renderScene();
  } catch (e) {
    alert("Speichern fehlgeschlagen: " + e.message);
  }
};

function escapeAttr(s) {
  return String(s ?? "").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

// ---------------------------------------------------------------------------
// Hilfen
// ---------------------------------------------------------------------------
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Start
fillStylePresets();
loadStatus();
loadSeriesList();
