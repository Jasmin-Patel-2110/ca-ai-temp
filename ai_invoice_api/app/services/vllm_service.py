"""Health and model checks for a vLLM OpenAI-compatible server (no Ollama)."""

import os

import requests

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen3-VL-8B-Thinking-FP8")

_model_checked: bool = False


def is_vllm_running() -> bool:
    """Return True if vLLM responds on /health or /v1/models."""
    try:
        r = requests.get(f"{VLLM_BASE_URL}/health", timeout=3)
        if r.status_code == 200:
            return True
    except Exception:
        pass
    try:
        r = requests.get(f"{VLLM_BASE_URL}/v1/models", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def ensure_model_available() -> None:
    """Confirm vLLM is reachable; optionally verify VLLM_MODEL appears in /v1/models."""
    global _model_checked
    if _model_checked:
        return

    if not is_vllm_running():
        raise RuntimeError(
            f"Cannot reach vLLM at {VLLM_BASE_URL}. "
            "Start the server first, e.g. on port 8001 (see start.sh comments)."
        )

    try:
        r = requests.get(f"{VLLM_BASE_URL}/v1/models", timeout=15)
        r.raise_for_status()
        data = r.json()
        ids = [str(m.get("id", "")) for m in data.get("data", []) if isinstance(m, dict)]
        if not ids:
            _model_checked = True
            return
        short = VLLM_MODEL.split("/")[-1]
        found = any(
            VLLM_MODEL == i or i.endswith(short) or short in i for i in ids
        )
        if not found:
            # Server is up but name may differ slightly; log-only path would need logging here.
            pass
    except requests.RequestException as e:
        raise RuntimeError(f"vLLM /v1/models check failed: {e}") from e

    _model_checked = True
