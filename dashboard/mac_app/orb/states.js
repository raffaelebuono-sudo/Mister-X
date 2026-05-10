// Visuelle Parameter pro JARVIS-Zustand.
// Farben sind als 0xRRGGBB-Werte für Three.js angegeben.

export const STATES = {
  sleeping: { color: 0x3a2a8c, accent: 0x6a4ad8, pulseHz: 0.35, scale: 0.95, rotation: 0.05 },
  listening:{ color: 0x4ab8ff, accent: 0x9be8ff, pulseHz: 1.6,  scale: 1.05, rotation: 0.20 },
  thinking: { color: 0x6a8aff, accent: 0xffffff, pulseHz: 1.0,  scale: 1.00, rotation: 1.20 },
  speaking: { color: 0xffffff, accent: 0x9bf0ff, pulseHz: 2.4,  scale: 1.10, rotation: 0.40 },
  error:    { color: 0xff3030, accent: 0xff8080, pulseHz: 5.0,  scale: 1.00, rotation: 0.10 },
  success:  { color: 0x40ff70, accent: 0xc0ffd0, pulseHz: 0.6,  scale: 1.05, rotation: 0.20 },
};

export const DEFAULT_STATE = 'sleeping';
