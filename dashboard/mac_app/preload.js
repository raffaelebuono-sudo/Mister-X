// Sicheres Bridging zwischen Renderer und Main-Prozess.
// Nur das Nötigste wird im Renderer als `window.jarvis` exponiert.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvis', {
  openDashboard: () => ipcRenderer.send('jarvis:open-dashboard'),
});
