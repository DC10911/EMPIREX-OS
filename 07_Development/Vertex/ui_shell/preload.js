// גשר מאובטח בין ה-renderer (חלון הצ'אט) לתהליך הראשי — contextIsolation מלא.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("vertexBridge", {
  getOrchestratorUrl: () => ipcRenderer.invoke("vertex:get-orchestrator-url"),
});
