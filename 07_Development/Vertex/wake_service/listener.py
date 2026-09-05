"""
wake_service/listener.py — שירות הרקע ל"היי וורטקס" (מפרט §2).

שירות עצמאי, מבודד (ר' §10א1), שמאזין ברציפות למיקרופון ברמת אנרגיה
נמוכה מאוד. שום אודיו לא נשלח לרשת לפני זיהוי ה-wake-word — הפרטיות
נשמרת כברירת מחדל. עם הזיהוי — שולח אירוע WAKE_DETECTED ל-Orchestrator
דרך WebSocket מקומי בלבד (127.0.0.1), ואז מפעיל STT להקלטת הפקודה.

דרישה מוקדמת: מודל ONNX מאומן על קול המשתמש (models/hey_vertex.onnx).
ר' wake_service/README.md לתהליך האימון (הקלטת 40-60 דוגמאות חיוביות
ו-200+ דוגמאות שליליות, ר' מפרט §2.2).
"""

import asyncio
import json
from pathlib import Path

import numpy as np
import sounddevice as sd
import websockets

WAKE_MODEL_PATH = Path(__file__).parent / "models" / "hey_vertex.onnx"
ORCHESTRATOR_WS_URL = "ws://127.0.0.1:8420/ws"
DEFAULT_THRESHOLD = 0.55


class VertexWakeService:
    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold
        self.active = False
        self.model = None
        self._loop: "asyncio.AbstractEventLoop | None" = None

    def _load_model(self):
        if not WAKE_MODEL_PATH.exists():
            raise FileNotFoundError(
                "מודל ה-wake-word לא נמצא. יש לאמן אותו קודם — ר' "
                "wake_service/README.md ו-wake_service/record_samples.py."
            )
        from openwakeword.model import Model  # type: ignore
        self.model = Model(wakeword_models=[str(WAKE_MODEL_PATH)])

    def audio_callback(self, indata, frames, time_info, status):
        audio = np.frombuffer(indata, dtype=np.int16)
        prediction = self.model.predict(audio)
        score = prediction.get("hey_vertex", 0.0)
        if score > self.threshold and not self.active and self._loop is not None:
            self.active = True
            asyncio.run_coroutine_threadsafe(self.on_wake_detected(score), self._loop)

    async def on_wake_detected(self, score: float):
        try:
            async with websockets.connect(ORCHESTRATOR_WS_URL) as ws:
                await ws.send(json.dumps({"type": "WAKE_DETECTED", "score": score}))
        except (ConnectionRefusedError, OSError):
            pass  # ה-Orchestrator לא רץ כרגע — לא חוסם את שירות ההאזנה
        self.active = False

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._load_model()
        with sd.RawInputStream(samplerate=16000, blocksize=1280, dtype="int16",
                                channels=1, callback=self.audio_callback):
            print("Vertex ממתין ל'היי וורטקס'...")
            while True:
                await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(VertexWakeService().run())
