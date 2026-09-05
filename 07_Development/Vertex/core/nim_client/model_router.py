"""
מטריצת ניתוב מודלים לפי סוג משימה (מפרט §15.4).
"""

MODEL_FOR_TASK = {
    "chat": "meta/llama-3.3-70b-instruct",
    "intent_classification": "meta/llama-3.3-70b-instruct",
    "browser_planning": "nvidia/nemotron-4-340b-instruct",
    "page_reading_vision": "meta/llama-3.2-90b-vision-instruct",
    "code_gen": "qwen/qwen2.5-coder-32b-instruct",
}


def model_for(task: str) -> str:
    return MODEL_FOR_TASK.get(task, MODEL_FOR_TASK["chat"])
