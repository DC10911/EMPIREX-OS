// Vertex Chat UI — renderer (מפרט §3.1–3.3, §16.1).
// מתחבר ל-Orchestrator המקומי דרך WebSocket, מציג בועות שיחה, פאנל
// משימות, וכרטיס אישור לפעולות הרסניות. כל טקסט/קול שמגיע מהסוכן — עברית.

const messagesEl = document.getElementById("messages");
const tasksListEl = document.getElementById("tasks-list");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const confirmBanner = document.getElementById("confirm-banner");
const confirmText = document.getElementById("confirm-text");
const confirmApprove = document.getElementById("confirm-approve");
const confirmReject = document.getElementById("confirm-reject");
const inputForm = document.getElementById("input-form");
const textInput = document.getElementById("text-input");
const micBtn = document.getElementById("mic-btn");

let ws = null;
let pendingConfirmTaskId = null;
const audioPlayer = new Audio();

function setStatus(mode, text) {
  statusDot.className = mode;
  statusText.textContent = text;
}

function addMessage(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `msg ${role}`;
  bubble.textContent = text;
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function upsertTask(taskId, label, statusValue) {
  let li = document.getElementById(`task-${taskId}`);
  if (!li) {
    li = document.createElement("li");
    li.id = `task-${taskId}`;
    tasksListEl.appendChild(li);
  }
  li.textContent = `${label || taskId} — ${statusValue}`;
}

async function connect() {
  const url = (window.vertexBridge && await window.vertexBridge.getOrchestratorUrl())
    || "ws://127.0.0.1:8420/ws";
  ws = new WebSocket(url);

  ws.onopen = () => setStatus("idle", "מחובר ל-Vertex — מוכן לפקודה");
  ws.onclose = () => setStatus("idle", "החיבור ל-Vertex נותק — מנסה שוב...");
  ws.onerror = () => setStatus("idle", "שגיאת חיבור ל-Vertex");

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleServerMessage(data);
  };
}

function handleServerMessage(data) {
  switch (data.type) {
    case "AGENT_REPLY":
      setStatus("idle", 'Vertex ממתין ל"היי וורטקס"...');
      addMessage("agent", data.text);
      if (data.audio_path) playAudio(data.audio_path);
      break;

    case "CONFIRM_REQUIRED":
      pendingConfirmTaskId = data.task_id;
      confirmText.textContent = data.flagged_external_source
        ? `⚠️ הדף/התוכן ניסה להנחות פעולה: ${data.action_desc} — לאשר?`
        : `⚠️ אישור נדרש: ${data.action_desc}`;
      confirmBanner.classList.remove("hidden");
      setStatus("thinking", "ממתין לאישור שלך...");
      break;

    case "TASK_UPDATE":
      upsertTask(data.task_id, data.task_label, data.current_step || "בתהליך");
      break;

    case "TASK_SUMMARY":
      upsertTask(data.task_id, data.task_label, "הושלם");
      addMessage("agent", `דוח מסכם: ${data.content}`);
      break;

    default:
      break;
  }
}

function playAudio(path) {
  // path הוא נתיב מקומי לקובץ mp3 שנוצר ע"י Hebrew TTS בצד השרת.
  audioPlayer.src = `file://${path}`;
  audioPlayer.play().catch(() => {});
}

function sendUserMessage(text, inputMode = "text") {
  if (!text.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;
  addMessage("user", text);
  setStatus("thinking", "Vertex חושב...");
  ws.send(JSON.stringify({
    type: "USER_MESSAGE",
    session_id: "local",
    input_mode: inputMode,
    text,
    timestamp: new Date().toISOString(),
  }));
}

inputForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendUserMessage(textInput.value);
  textInput.value = "";
});

confirmApprove.addEventListener("click", () => {
  ws.send(JSON.stringify({ type: "CONFIRM_RESOLVE", task_id: pendingConfirmTaskId, approved: true }));
  confirmBanner.classList.add("hidden");
});

confirmReject.addEventListener("click", () => {
  ws.send(JSON.stringify({ type: "CONFIRM_RESOLVE", task_id: pendingConfirmTaskId, approved: false }));
  confirmBanner.classList.add("hidden");
});

// כפתור מיקרופון — הקלטה קצרה ושליחה ל-STT בצד השרת (Phase 1: placeholder UI;
// שילוב מלא מול wake_service/STT מתבצע כשה-wake service רץ ברקע).
let recording = false;
micBtn.addEventListener("click", () => {
  recording = !recording;
  micBtn.classList.toggle("active", recording);
  setStatus(recording ? "listening" : "idle",
    recording ? "מקשיב..." : 'Vertex ממתין ל"היי וורטקס"...');
});

connect();
