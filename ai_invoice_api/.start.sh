#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Invoice AI — Startup Script
#  Optimized for AWS g5.xlarge / g6.xlarge (NVIDIA A10G / L4 GPU)
#
#  Two Ollama instances:
#    Port 11434 → adelnazmy2002/Qwen3-VL-8B-Instruct (main extraction)
#    Port 11435 → qwen2.5:0.5b-invoice-category       (category)
#
#  Usage:
#    chmod +x start.sh
#    ./start.sh                                  (foreground)
#    nohup ./start.sh > logs/startup.log 2>&1 &  (background)
#    pm2 start start.sh --name ca-ai-api         (PM2 managed)
# ═══════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"

# ── Models ────────────────────────────────────────────────────
MAIN_MODEL="adelnazmy2002/Qwen3-VL-8B-Instruct"
CATEGORY_MODEL="${OLLAMA_CATEGORY_MODEL:-qwen2.5:0.5b-invoice-category}"

# ── Ports ─────────────────────────────────────────────────────
MAIN_PORT=11434
CATEGORY_PORT=11435

# ── Timing ────────────────────────────────────────────────────
OLLAMA_READY_TIMEOUT=15
OLLAMA_READY_INTERVAL=1
WARMUP_TIMEOUT=45

# ── Colors ────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

ok()   { echo -e "${GREEN}[OK]${NC}  $1"; }
info() { echo -e "${YELLOW}[..]${NC}  $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }

STARTUP_TIME=$SECONDS

echo "════════════════════════════════════════"
echo "   Invoice AI Startup"
echo "   Script dir: $SCRIPT_DIR"
echo "════════════════════════════════════════"

# ═══════════════════════════════════════════════════════════════
# 1. Install Ollama (only if not already installed)
# ═══════════════════════════════════════════════════════════════
if command -v ollama &> /dev/null; then
    ok "Ollama already installed ($(ollama --version 2>/dev/null || echo 'unknown'))"
else
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama installed"
fi

# ═══════════════════════════════════════════════════════════════
# 2. GPU Performance tuning
# ═══════════════════════════════════════════════════════════════
export OLLAMA_NUM_GPU=999
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_MAX_LOADED_MODELS=1
export CUDA_VISIBLE_DEVICES=0
ok "GPU env set (NUM_GPU=999, FLASH_ATTENTION=1)"

# ═══════════════════════════════════════════════════════════════
# 3. Start both Ollama instances simultaneously
# ═══════════════════════════════════════════════════════════════
start_ollama_instance() {
    local PORT=$1
    local LABEL=$2
    local LOGFILE="$LOG_DIR/ollama_${PORT}.log"

    if curl -s --max-time 2 "http://localhost:${PORT}/api/tags" > /dev/null 2>&1; then
        ok "Ollama ${LABEL} already running on port ${PORT}"
        return 0
    fi

    info "Starting Ollama ${LABEL} on port ${PORT}..."

    OLLAMA_HOST="0.0.0.0:${PORT}" \
    OLLAMA_KEEP_ALIVE="60m" \
    OLLAMA_NUM_GPU=999 \
    OLLAMA_FLASH_ATTENTION=1 \
    OLLAMA_MAX_LOADED_MODELS=1 \
    nohup ollama serve > "$LOGFILE" 2>&1 &

    echo $! > "$LOG_DIR/ollama_${PORT}.pid"
}

wait_for_ollama() {
    local PORT=$1
    local LABEL=$2
    local ELAPSED=0

    while [ $ELAPSED -lt $OLLAMA_READY_TIMEOUT ]; do
        if curl -s --max-time 2 "http://localhost:${PORT}/api/tags" > /dev/null 2>&1; then
            ok "Ollama ${LABEL} ready on port ${PORT} (${ELAPSED}s)"
            return 0
        fi
        sleep $OLLAMA_READY_INTERVAL
        ELAPSED=$((ELAPSED + OLLAMA_READY_INTERVAL))
    done

    err "Ollama ${LABEL} (port ${PORT}) not ready after ${OLLAMA_READY_TIMEOUT}s"
    err "Check log: $LOG_DIR/ollama_${PORT}.log"
    exit 1
}

# Start both simultaneously
start_ollama_instance $MAIN_PORT     "main-extraction"
start_ollama_instance $CATEGORY_PORT "category-model"

# Wait for both to be ready
wait_for_ollama $MAIN_PORT     "main-extraction"
wait_for_ollama $CATEGORY_PORT "category-model"

# ═══════════════════════════════════════════════════════════════
# 4. Pull / verify models
# ═══════════════════════════════════════════════════════════════
pull_model_if_missing() {
    local PORT=$1
    local MODEL=$2
    local LABEL=$3

    EXISTING=$(curl -s "http://localhost:${PORT}/api/tags" | python3 -c "
import sys,json
print('\n'.join(m['name'] for m in json.load(sys.stdin).get('models',[])))
" 2>/dev/null || echo "")

    if echo "$EXISTING" | grep -qF "$MODEL"; then
        ok "${LABEL} model '${MODEL}' already available"
        return
    fi

    ALL=$(curl -s "http://localhost:${MAIN_PORT}/api/tags" | python3 -c "
import sys,json
print('\n'.join(m['name'] for m in json.load(sys.stdin).get('models',[])))
" 2>/dev/null || echo "")

    if echo "$ALL" | grep -qF "$MODEL"; then
        ok "${LABEL} model '${MODEL}' found in local storage"
        return
    fi

    info "Pulling ${LABEL} model '${MODEL}'..."
    if ollama pull "$MODEL" 2>/dev/null; then
        ok "${LABEL} model '${MODEL}' pulled"
    else
        err "Could not pull '${MODEL}'"
        err "If local model run: ollama create ${MODEL} -f Modelfile"
        exit 1
    fi
}

pull_model_if_missing $MAIN_PORT     "$MAIN_MODEL"     "main"
pull_model_if_missing $CATEGORY_PORT "$CATEGORY_MODEL" "category"

# ═══════════════════════════════════════════════════════════════
# 5. Warmup both models in parallel (hard timeout — never hangs)
# ═══════════════════════════════════════════════════════════════
info "Warming up models in parallel (timeout: ${WARMUP_TIMEOUT}s)..."

warmup_model() {
    local PORT=$1
    local MODEL=$2
    local LABEL=$3
    local START=$SECONDS

    if timeout $WARMUP_TIMEOUT curl -s \
        --max-time $WARMUP_TIMEOUT \
        "http://localhost:${PORT}/api/generate" \
        -d "{\"model\":\"${MODEL}\",\"prompt\":\"hi\",\"stream\":false,\"keep_alive\":\"60m\",\"options\":{\"num_predict\":1,\"num_ctx\":512}}" \
        > /dev/null 2>&1; then
        ok "${LABEL} warm in VRAM — $((SECONDS - START))s"
    else
        info "${LABEL} warmup timed out — model loads on first real request"
    fi
}

warmup_model $MAIN_PORT     "$MAIN_MODEL"     "Main model"     &
WARMUP_MAIN=$!
warmup_model $CATEGORY_PORT "$CATEGORY_MODEL" "Category model" &
WARMUP_CAT=$!

wait $WARMUP_MAIN 2>/dev/null || true
wait $WARMUP_CAT  2>/dev/null || true

# ═══════════════════════════════════════════════════════════════
# 6. GPU verification
# ═══════════════════════════════════════════════════════════════
if command -v nvidia-smi &> /dev/null; then
    GPU_MEM=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
    ok "GPU: ${GPU_MEM} MiB used | util: ${GPU_UTIL}%"
    if [ "${GPU_MEM:-0}" -lt 1000 ]; then
        err "WARNING: GPU memory < 1GB — models may be running on CPU!"
    fi
fi

# ═══════════════════════════════════════════════════════════════
# 7. Python virtual environment
#    ── FIX: priority order — NVMe → local → system ─────────────
#    Your venv is at /opt/dlami/nvme/venv (NVMe disk).
#    The old script only checked $SCRIPT_DIR/venv which doesn't
#    exist, so it fell back to system Python (no uvicorn).
# ═══════════════════════════════════════════════════════════════
NVME_VENV="/opt/dlami/nvme/venv"
LOCAL_VENV="$SCRIPT_DIR/venv"
UVICORN_BIN=""

if [ -f "$NVME_VENV/bin/uvicorn" ]; then
    source "$NVME_VENV/bin/activate"
    UVICORN_BIN="$NVME_VENV/bin/uvicorn"
    ok "Virtual environment activated (NVMe: $NVME_VENV)"
elif [ -f "$LOCAL_VENV/bin/uvicorn" ]; then
    source "$LOCAL_VENV/bin/activate"
    UVICORN_BIN="$LOCAL_VENV/bin/uvicorn"
    ok "Virtual environment activated (local: $LOCAL_VENV)"
elif command -v uvicorn &> /dev/null; then
    UVICORN_BIN="$(command -v uvicorn)"
    ok "Using system uvicorn: $UVICORN_BIN"
else
    err "uvicorn not found in any venv or system Python!"
    err "Run: source /opt/dlami/nvme/venv/bin/activate && pip install 'uvicorn[standard]' fastapi"
    exit 1
fi

ok "uvicorn found at: $UVICORN_BIN"

# ═══════════════════════════════════════════════════════════════
# 8. Load .env file
# ═══════════════════════════════════════════════════════════════
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -o allexport
    source "$SCRIPT_DIR/.env"
    set +o allexport
    ok ".env loaded from $SCRIPT_DIR/.env"
else
    info "No .env found at $SCRIPT_DIR/.env — using environment variables only"
fi

# ═══════════════════════════════════════════════════════════════
# 9. Export app environment variables
# ═══════════════════════════════════════════════════════════════
export OLLAMA_BASE_URL="http://localhost:${MAIN_PORT}"
export OLLAMA_CATEGORY_BASE_URL="http://localhost:${CATEGORY_PORT}"
export OLLAMA_MODEL="$MAIN_MODEL"
export OLLAMA_CATEGORY_MODEL="$CATEGORY_MODEL"
export OLLAMA_KEEP_ALIVE=60m
export EXTRACTION_WORKERS=3
export OLLAMA_NUM_PARALLEL=3
export OLLAMA_MAX_RETRIES=3
export OLLAMA_RETRY_BACKOFF=2.0
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# ═══════════════════════════════════════════════════════════════
# 10. Start FastAPI using the full uvicorn path
#     ── FIX: use $UVICORN_BIN (full path) not bare `uvicorn`
#     Bare `uvicorn` fails when PM2 runs the script because
#     the activated venv PATH is not inherited by exec.
# ═══════════════════════════════════════════════════════════════
TOTAL=$((SECONDS - STARTUP_TIME))

echo ""
echo "════════════════════════════════════════"
ok "Ready in ${TOTAL}s — Starting FastAPI..."
echo ""
echo "  Script dir: $SCRIPT_DIR"
echo "  Uvicorn:    $UVICORN_BIN"
echo "  API:        http://0.0.0.0:8000"
echo "  Docs:       http://<ec2-ip>:8000/docs"
echo "  Ollama 1:   http://localhost:${MAIN_PORT}  (extraction)"
echo "  Ollama 2:   http://localhost:${CATEGORY_PORT} (category)"
echo "  Logs:       $LOG_DIR/"
echo "════════════════════════════════════════"

cd "$SCRIPT_DIR"

exec "$UVICORN_BIN" app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info \
    --access-log
