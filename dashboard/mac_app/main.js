// JARVIS – Electron-Hauptprozess
//
// Erzeugt zwei Fenster:
//   1. Schwebende Kugel (immer im Vordergrund, klein, randlos, transparent)
//   2. Dashboard (auf Klick der Kugel)
//
// Drag und Klick werden in JS erkannt (CSS drag region schluckt auf
// macOS leider Maus-Events) – siehe IPC-Handler unten und orb/orb.js.

const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('node:path');

let orbWindow = null;
let dashboardWindow = null;
let dragOffset = null;   // { dx, dy } – Mausposition relativ zur Fenster-Ecke beim Drag-Start

function createOrbWindow() {
  const display = screen.getPrimaryDisplay();
  const { workArea } = display;
  orbWindow = new BrowserWindow({
    width: 200,
    height: 200,
    x: workArea.x + workArea.width - 220,
    y: workArea.y + 80,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    hasShadow: false,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });
  orbWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  orbWindow.loadFile(path.join(__dirname, 'orb', 'index.html'));
}

function createDashboardWindow() {
  if (dashboardWindow) {
    dashboardWindow.show();
    dashboardWindow.focus();
    return;
  }
  dashboardWindow = new BrowserWindow({
    width: 1200,
    height: 780,
    minWidth: 980,
    minHeight: 640,
    title: 'JARVIS Dashboard',
    backgroundColor: '#0a0e1a',
    webPreferences: { contextIsolation: true },
  });
  dashboardWindow.loadFile(path.join(__dirname, 'ui', 'dashboard.html'));
  dashboardWindow.on('closed', () => { dashboardWindow = null; });
}

app.whenReady().then(() => {
  createOrbWindow();
  ipcMain.on('jarvis:open-dashboard', () => createDashboardWindow());

  // JS-gesteuertes Verschieben der Kugel.
  // Renderer schickt Bildschirmkoordinaten der Maus mit – Hauptprozess
  // bewegt das Fenster, sodass die Maus an derselben Stelle des Fensters bleibt.
  ipcMain.on('jarvis:drag-start', (_e, mouseX, mouseY) => {
    if (!orbWindow) return;
    const [winX, winY] = orbWindow.getPosition();
    dragOffset = { dx: mouseX - winX, dy: mouseY - winY };
  });
  ipcMain.on('jarvis:drag', (_e, mouseX, mouseY) => {
    if (!orbWindow || !dragOffset) return;
    orbWindow.setPosition(
      Math.round(mouseX - dragOffset.dx),
      Math.round(mouseY - dragOffset.dy),
    );
  });
  ipcMain.on('jarvis:drag-end', () => { dragOffset = null; });
});

// Auf macOS bleiben Apps üblicherweise aktiv; wir schließen nicht beim
// Schließen aller Fenster.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
