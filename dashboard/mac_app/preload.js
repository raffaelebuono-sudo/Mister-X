// Sicheres Bridging zwischen Renderer und Main-Prozess.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvis', {
  // Der Renderer schickt dieses Event, wenn der Backend-WebSocket
  // 'activate' meldet (Wake-Word oder Klatschen). Main fokussiert das Fenster.
  focus: () => ipcRenderer.send('jarvis:focus'),
});
