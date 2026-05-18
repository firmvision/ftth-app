const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("electronAPI", {
  saveFile: (filename, content, mimeType) => ipcRenderer.invoke("save-file", { filename, content, mimeType }),
  openFile: () => ipcRenderer.invoke("open-file"),
  platform: process.platform
});
