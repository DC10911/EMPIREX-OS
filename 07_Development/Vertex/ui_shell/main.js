// Vertex UI Shell — Electron main process (מפרט §3, §15.3).
// חלון מלא-מסך דמוי-Gemini, tray icon תמידי, ללא פתיחת תיקיית התקנה מחדש
// בכל הפעלה (§10 — ההפעלה היא דרך קיצור דרך/tray icon בלבד).

const { app, BrowserWindow, Tray, Menu, ipcMain } = require("electron");
const path = require("path");

let mainWindow = null;
let tray = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 780,
    title: "Vertex",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile(path.join(__dirname, "src", "index.html"));

  mainWindow.on("close", (event) => {
    // סגירה = מזעור למגש, לא יציאה — Vertex ממשיך להאזין ברקע
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  tray = new Tray(path.join(__dirname, "..", "installer", "assets", "icon.png"));
  const menu = Menu.buildFromTemplate([
    { label: "פתח את Vertex", click: () => mainWindow.show() },
    { label: "יציאה", click: () => { app.isQuitting = true; app.quit(); } },
  ]);
  tray.setToolTip("Vertex — סוכן AI אישי");
  tray.setContextMenu(menu);
  tray.on("click", () => mainWindow.show());
}

app.whenReady().then(() => {
  createWindow();
  createTray();
});

app.on("window-all-closed", (e) => e.preventDefault());

ipcMain.handle("vertex:get-orchestrator-url", () => "ws://127.0.0.1:8420/ws");
