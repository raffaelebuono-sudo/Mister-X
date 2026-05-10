// Sicheres Bridging zwischen Renderer und Main-Prozess.
// Nur das Nötigste wird im Renderer als `window.jarvis` exponiert.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvis', {
  openDashboard: () => ipcRenderer.send('jarvis:open-dashboard'),
  // JS-gesteuertes Verschieben (zuverlässiger als CSS-Drag-Region auf macOS)
  dragStart: (mouseX, mouseY) => ipcRenderer.send('jarvis:drag-start', mouseX, mouseY),
  drag: (mouseX, mouseY) => ipcRenderer.send('jarvis:drag', mouseX, mouseY),
  dragEnd: () => ipcRenderer.send('jarvis:drag-end'),
});
