const { app, BrowserWindow, Menu, shell, ipcMain, dialog, nativeTheme } = require("electron");
const path = require("path");
const fs   = require("fs");

nativeTheme.themeSource = "dark";
let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440, height: 900, minWidth: 900, minHeight: 600,
    title: "FTTH GIS Route Planner",
    backgroundColor: "#04090F",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  mainWindow.loadFile(path.join(__dirname, "..", "index.html"));
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) shell.openExternal(url);
    return { action: "deny" };
  });
}

ipcMain.handle("save-file", async (event, { filename, content }) => {
  const ext = path.extname(filename);
  const filters = ext === ".geojson" ? [{ name:"GeoJSON", extensions:["geojson","json"] }]
                : ext === ".kml"     ? [{ name:"KML",     extensions:["kml"] }]
                : ext === ".csv"     ? [{ name:"CSV",     extensions:["csv"] }]
                : [{ name:"All Files", extensions:["*"] }];
  const { filePath, canceled } = await dialog.showSaveDialog(mainWindow, {
    defaultPath: path.join(app.getPath("documents"), filename), filters
  });
  if (canceled || !filePath) return { success: false };
  try { fs.writeFileSync(filePath, content, "utf-8"); return { success: true, filePath }; }
  catch (err) { return { success: false, reason: err.message }; }
});

ipcMain.handle("open-file", async () => {
  const { filePaths, canceled } = await dialog.showOpenDialog(mainWindow, {
    filters: [{ name:"FTTH Design", extensions:["json","geojson"] }],
    properties: ["openFile"]
  });
  if (canceled || !filePaths.length) return null;
  try { return fs.readFileSync(filePaths[0], "utf-8"); } catch { return null; }
});

app.whenReady().then(() => {
  createWindow();
  const isMac = process.platform === "darwin";
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    ...(isMac ? [{ label: app.name, submenu: [{ role:"about" },{ type:"separator" },{ role:"quit" }] }] : []),
    { label:"File", submenu:[
      { label:"New Plan",        accelerator:"CmdOrCtrl+N", click: () => mainWindow.reload() },
      { label:"Save Plan",       accelerator:"CmdOrCtrl+S", click: () => mainWindow.webContents.executeJavaScript('document.getElementById("btn-save")?.click()') },
      { label:"Open Plan",       accelerator:"CmdOrCtrl+O", click: () => mainWindow.webContents.executeJavaScript('document.getElementById("btn-load")?.click()') },
      { type:"separator" },
      { label:"Export GeoJSON",  click: () => mainWindow.webContents.executeJavaScript('document.getElementById("btn-geojson")?.click()') },
      { label:"Export KML",      click: () => mainWindow.webContents.executeJavaScript('document.getElementById("btn-kml")?.click()') },
      { label:"Export CSV BoM",  click: () => mainWindow.webContents.executeJavaScript('document.getElementById("btn-csv")?.click()') },
      { type:"separator" },
      isMac ? { role:"close" } : { role:"quit" }
    ]},
    { label:"View", submenu:[{ role:"reload" },{ role:"togglefullscreen" }] }
  ]));
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
