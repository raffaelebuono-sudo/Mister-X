// JARVIS – Electron-Hauptprozess
//
// Eine App, ein Fenster: das Dashboard. Wird beim Start direkt geöffnet,
// kommt nach vorne wenn JARVIS aktiviert wird (Wake-Word oder Klatschen).
// Keine schwebende Kugel mehr – die Kugel lebt jetzt im Dashboard.

const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('node:path');

let dashboardWindow = null;

function createDashboardWindow() {
  const display = screen.getPrimaryDisplay();
  const { workArea } = display;
  const width = Math.min(1280, workArea.width);
  const height = Math.min(820, workArea.height);
  dashboardWindow = new BrowserWindow({
    width,
    height,
    minWidth: 1024,
    minHeight: 720,
    x: workArea.x + Math.floor((workArea.width - width) / 2),
    y: workArea.y + Math.floor((workArea.height - height) / 2),
    title: 'JARVIS',
    backgroundColor: '#02050d',
    titleBarStyle: 'hiddenInset',
    vibrancy: 'under-window',
    visualEffectState: 'active',
    webPreferences: {
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  dashboardWindow.loadFile(path.join(__dirname, 'ui', 'dashboard.html'));
  dashboardWindow.on('closed', () => { dashboardWindow = null; });
}

function focusDashboard() {
  if (!dashboardWindow) {
    createDashboardWindow();
    return;
  }
  if (dashboardWindow.isMinimized()) dashboardWindow.restore();
  dashboardWindow.show();
  dashboardWindow.focus();
  app.focus({ steal: true });
}

app.whenReady().then(() => {
  createDashboardWindow();
  ipcMain.on('jarvis:focus', focusDashboard);
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createDashboardWindow();
});
