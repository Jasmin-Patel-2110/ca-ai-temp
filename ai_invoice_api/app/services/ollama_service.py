import os
import requests

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL   = os.getenv("OLLAMA_MODEL","qwen2.5vl:7b")

# In-process flag — True once the model has been confirmed/pulled this session.
# Avoids repeated network calls on every upload request.
_model_ready: bool = False


def ensure_model_pulled(model: str = DEFAULT_MODEL) -> None:
    """Confirm the Ollama model is available locally, pulling it if needed.

    This is a ONE-TIME operation per server session:
    - First request  → checks /api/tags; pulls if model is absent (~minutes)
    - All subsequent requests → returns immediately (flag already set)
    """
    global _model_ready
    if _model_ready:
        return

    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        resp.raise_for_status()
        existing = [m["name"] for m in resp.json().get("models", [])]

        # Normalize: "qwen2.5vl:7b" matches "qwen2.5vl:7b" or "qwen2.5vl"
        model_base = model.split(":")[0]
        already_pulled = any(
            m == model or m.startswith(model_base) for m in existing
        )

        if not already_pulled:
            print(f"[ollama] Pulling model {model!r} — this may take a few minutes...")
            pull_resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"name": model},
                stream=True,
                timeout=600,   # 10-minute timeout for large models
            )
            pull_resp.raise_for_status()
            # Drain the streaming response so the pull completes fully
            for _ in pull_resp.iter_lines():
                pass
            print(f"[ollama] Model {model!r} pulled successfully.")
        else:
            print(f"[ollama] Model {model!r} already available.")

    except requests.RequestException as e:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. "
            f"Make sure 'ollama serve' is running. Error: {e}"
        )

    _model_ready = True


def is_ollama_running() -> bool:
    """Quick health check — returns True if Ollama is reachable."""
    try:
        requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return True
    except Exception:
        return False
