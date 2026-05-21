from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path


_LOCK = threading.Lock()
_PENDING = 0
_TRAINING = False


def _project_root() -> Path:
    # app/services/ml_retrain_service.py -> project root
    return Path(__file__).resolve().parents[2]


def _run_retrain_script() -> None:
    root = _project_root()
    py = sys.executable
    subprocess.run(
        [py, "scripts/train_river_category_subcategory.py"],
        cwd=str(root),
        check=False,
    )


def _train_worker() -> None:
    global _TRAINING
    try:
        _run_retrain_script()
    finally:
        with _LOCK:
            _TRAINING = False


def request_ml_retrain(increment: int = 1) -> None:
    """
    Queue an async sklearn retrain trigger.

    Env vars:
      ML_AUTO_RETRAIN_ON_UPLOAD=1|0  (default 1)
      ML_RETRAIN_EVERY_N=<int>       (default 1)
    """
    global _PENDING, _TRAINING

    if str(os.getenv("ML_AUTO_RETRAIN_ON_UPLOAD", "1")).strip() not in ("1", "true", "True"):
        return

    try:
        every_n = max(1, int(os.getenv("ML_RETRAIN_EVERY_N", "1")))
    except Exception:
        every_n = 1

    with _LOCK:
        _PENDING += max(0, int(increment))
        if _TRAINING:
            return
        if _PENDING < every_n:
            return
        _PENDING = 0
        _TRAINING = True

    t = threading.Thread(target=_train_worker, daemon=True)
    t.start()

