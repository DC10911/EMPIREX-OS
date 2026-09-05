"""
NVIDIA NIM API Client — עם Retry, Backoff ומעקב עלות (מפרט §22.3).

המפתח (api_key) נטען מהגדרות מוצפנות (Windows Credential Manager / DPAPI
בפרודקשן, ר' core/config.py) — לעולם לא הארדקוד ולעולם לא בלוג.
"""

import time
from dataclasses import dataclass, field

import requests

BASE_URL = "https://integrate.api.nvidia.com/v1"

# חובה: יש להזין תעריפים בפועל מול המחירון העדכני של NVIDIA בזמן ההטמעה.
DEFAULT_COST_TABLE = {
    "meta/llama-3.3-70b-instruct": {"in": 0.0, "out": 0.0},
    "nvidia/nemotron-4-340b-instruct": {"in": 0.0, "out": 0.0},
    "meta/llama-3.2-90b-vision-instruct": {"in": 0.0, "out": 0.0},
    "qwen/qwen2.5-coder-32b-instruct": {"in": 0.0, "out": 0.0},
}


@dataclass
class NimUsageRecord:
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: float
    estimated_cost_usd: float


class UsageLogger:
    def __init__(self):
        self.records: list[NimUsageRecord] = field(default_factory=list)
        self.records = []

    def log(self, record: NimUsageRecord):
        self.records.append(record)

    def total_cost(self) -> float:
        return sum(r.estimated_cost_usd for r in self.records)


class NimClient:
    def __init__(self, api_key: str, cost_table: "dict | None" = None,
                 usage_logger: "UsageLogger | None" = None):
        self.api_key = api_key
        self.cost_table = cost_table or DEFAULT_COST_TABLE
        self.usage_logger = usage_logger or UsageLogger()
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def chat_completion(self, model: str, messages: list[dict],
                         max_retries: int = 3, timeout: int = 30) -> dict:
        last_exc: "Exception | None" = None
        for attempt in range(max_retries):
            try:
                resp = self.session.post(
                    f"{BASE_URL}/chat/completions",
                    json={"model": model, "messages": messages, "temperature": 0.3},
                    timeout=timeout,
                )
                if resp.status_code == 429:
                    time.sleep((2 ** attempt) * 1.5)
                    continue
                resp.raise_for_status()
                data = resp.json()
                self._record_usage(model, data.get("usage", {}))
                return data
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        raise ConnectionError(f"NIM API נכשל אחרי {max_retries} ניסיונות: {last_exc}")

    def _record_usage(self, model: str, usage: dict):
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        rates = self.cost_table.get(model, {"in": 0, "out": 0})
        cost = (in_tok / 1_000_000) * rates["in"] + (out_tok / 1_000_000) * rates["out"]
        self.usage_logger.log(NimUsageRecord(model, in_tok, out_tok, time.time(), cost))

    def extract_text(self, response: dict) -> str:
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return ""
