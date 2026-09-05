"""
כלי עזר להקלטת דוגמאות אימון ל-wake-word "היי וורטקס" (מפרט §2.2).

הרצה:  python record_samples.py --label positive --count 50
        python record_samples.py --label negative --count 200

דוגמאות positive: אמור/אמרי "היי וורטקס" בגוונים/מרחקים/רעשי רקע שונים.
דוגמאות negative: דיבור רגיל, טלוויזיה, מוזיקה — כל דבר שאינו "היי וורטקס".

לאחר ההקלטה יש להריץ את openwakeword training pipeline (מתועד ב-
wake_service/README.md) כדי לייצר את models/hey_vertex.onnx.
"""

import argparse
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
DURATION_SEC = 2.0


def record_one(out_path: Path):
    print(f"מקליט 2 שניות... אמור/אמרי עכשיו -> {out_path.name}")
    audio = sd.rec(int(DURATION_SEC * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                    channels=1, dtype="int16")
    sd.wait()
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


def main():
    parser = argparse.ArgumentParser(description="הקלטת דוגמאות אימון ל-wake-word של Vertex")
    parser.add_argument("--label", choices=["positive", "negative"], required=True)
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--out-dir", default="./training_samples")
    args = parser.parse_args()

    out_dir = Path(args.out_dir) / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(args.count):
        input(f"[{i + 1}/{args.count}] הקש Enter כשמוכן/ה... ")
        record_one(out_dir / f"{args.label}_{i:04d}.wav")

    print(f"הושלם: {args.count} דוגמאות '{args.label}' נשמרו ב-{out_dir}")


if __name__ == "__main__":
    main()
