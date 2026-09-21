#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Docker image entrypoint runs before repository exists. Preserve Runpod base startup.
if [[ ! -d "${SCRIPT_DIR}/Frontend" || ! -d "${SCRIPT_DIR}/ai_invoice_api" ]]; then
    exec /start.sh "$@"
fi

ROOT_DIR="${SCRIPT_DIR}"
ENV_FILE="${ROOT_DIR}/.env.runpod"
VENV_DIR="${VENV_DIR:-/workspace/venvs/ca-ai}"
DATA_DIR="${DATA_DIR:-/workspace/ca-ai-data}"
MYSQL_DATA_DIR="${MYSQL_DATA_DIR:-/var/lib/mysql}"
PM2_CONFIG="${ROOT_DIR}/deploy/runpod/ecosystem.config.cjs"

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Run as root: sudo ./start-services.sh ${1:-setup}" >&2
        exit 1
    fi
}

load_env() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "Missing ${ENV_FILE}. Run ./start-services.sh setup first." >&2
        exit 1
    fi
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
    export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
    export no_proxy="${no_proxy:-${NO_PROXY}}"
}

local_curl() {
    curl --noproxy '*' "$@"
}

create_env() {
    if [[ -f "${ENV_FILE}" ]]; then
        return
    fi

    local secret db_password
    secret="$(openssl rand -hex 32)"
    db_password="$(openssl rand -hex 24)"
    cat > "${ENV_FILE}" <<EOF
ENVIRONMENT=production
SECRET_KEY=${secret}
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=invoice_app
DB_PASSWORD=${db_password}
DB_NAME=invoice_api
MYSQL_DATA_DIR=/var/lib/mysql
API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_API_URL=
CORS_ORIGINS=
NO_PROXY=127.0.0.1,localhost
no_proxy=127.0.0.1,localhost
VLLM_BASE_URL=http://127.0.0.1:8001
VLLM_MODEL=Qwen/Qwen3-VL-8B-Thinking-FP8
VLLM_MAX_MODEL_LEN=32768
VLLM_GPU_MEMORY_UTILIZATION=0.90
VLLM_MAX_NUM_SEQS=4
VLLM_MAX_PIXELS=602112
VLLM_MAX_OUTPUT_TOKENS=8192
HF_HOME=/workspace/huggingface
CHROMA_DIR=${DATA_DIR}/chroma
DOCUMENT_STORAGE_DIR=${DATA_DIR}/documents
EMBEDDING_DEVICE=cpu
HF_TOKEN=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-south-1
S3_BUCKET_NAME=
INVOICE_BOOK_COMPANY_NAME=
EOF
    chmod 600 "${ENV_FILE}"
    echo "Created ${ENV_FILE}"
}

install_dependencies() {
    load_env
    apt-get update
    apt-get install -y --no-install-recommends \
        git curl openssl python3.12 python3.12-dev python3.12-venv \
        nginx mariadb-server build-essential pkg-config libmariadb-dev psmisc
    rm -rf /var/lib/apt/lists/*

    mkdir -p "$(dirname "${VENV_DIR}")" "${DATA_DIR}" /workspace/huggingface
    if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
        python3.12 -m venv "${VENV_DIR}"
    fi
    "${VENV_DIR}/bin/pip" install --upgrade pip wheel
    "${VENV_DIR}/bin/pip" install --upgrade vllm -r "${ROOT_DIR}/ai_invoice_api/requirements.txt"
    command -v pm2 >/dev/null || npm install --global pm2

    npm --prefix "${ROOT_DIR}/Frontend" ci
    npm --prefix "${ROOT_DIR}/Frontend" run build
}

configure_database() {
    load_env
    [[ "${DB_NAME}" =~ ^[A-Za-z0-9_]+$ ]] || { echo "Invalid DB_NAME" >&2; exit 1; }
    [[ "${DB_USER}" =~ ^[A-Za-z0-9_]+$ ]] || { echo "Invalid DB_USER" >&2; exit 1; }
    [[ "${DB_PASSWORD}" =~ ^[A-Fa-f0-9]+$ ]] || { echo "DB_PASSWORD must be hexadecimal" >&2; exit 1; }

    service mariadb stop >/dev/null 2>&1 || true
    install -d -o mysql -g mysql -m 0750 "${MYSQL_DATA_DIR}"
    install -d -o mysql -g mysql -m 0755 /run/mysqld
    if [[ ! -d "${MYSQL_DATA_DIR}/mysql" ]]; then
        mariadb-install-db --user=mysql --datadir="${MYSQL_DATA_DIR}" --skip-test-db
    fi
    cat > /etc/mysql/mariadb.conf.d/99-ca-ai-runpod.cnf <<EOF
[mysqld]
datadir=${MYSQL_DATA_DIR}
bind-address=127.0.0.1
port=3306
socket=/run/mysqld/mysqld.sock
pid-file=/run/mysqld/mysqld.pid
EOF
    service mariadb start

    for _ in {1..30}; do
        mariadb-admin --socket=/run/mysqld/mysqld.sock ping --silent && break
        sleep 1
    done
    mariadb-admin --socket=/run/mysqld/mysqld.sock ping --silent
    mariadb --socket=/run/mysqld/mysqld.sock <<SQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL
}

configure_nginx() {
    # RunPod's base image replaces the Ubuntu main config with proxy servers
    # for ports already owned by its other services. Use an isolated config so
    # those inherited listeners cannot collide with this application.
    install -m 0644 "${ROOT_DIR}/deploy/runpod/nginx.conf" /etc/nginx/nginx.conf
    nginx -t
    service nginx restart
}

start_processes() {
    load_env
    [[ -x "${VENV_DIR}/bin/vllm" ]] || { echo "Missing vLLM environment. Run setup." >&2; exit 1; }
    if ! command -v fuser >/dev/null 2>&1; then
        apt-get update
        apt-get install -y --no-install-recommends psmisc
        rm -rf /var/lib/apt/lists/*
    fi
    command -v fuser >/dev/null 2>&1 || { echo "Missing fuser; install psmisc" >&2; exit 1; }
    [[ -f "${ROOT_DIR}/Frontend/.next/BUILD_ID" ]] || { echo "Missing frontend build. Run setup." >&2; exit 1; }

    mkdir -p "${CHROMA_DIR}" "${HF_HOME}"
    pm2 delete ca-ai-vllm ca-ai-backend ca-ai-frontend >/dev/null 2>&1 || true
    # vLLM can leave its API-server child alive after PM2 stops the launcher.
    # Clear dedicated internal ports before starting a fresh process set.
    fuser -k 3001/tcp 8000/tcp 8001/tcp >/dev/null 2>&1 || true
    pm2 start "${PM2_CONFIG}" --update-env
    pm2 save --force

    for _ in {1..60}; do
        if local_curl --fail --silent --max-time 5 http://127.0.0.1:8000/ >/dev/null \
            && local_curl --fail --silent --max-time 5 http://127.0.0.1:3001/ >/dev/null; then
            echo "Frontend and API ready. vLLM continues loading model in background."
            echo "Open Runpod HTTP port 3000. Check model: ./start-services.sh status"
            return
        fi
        sleep 2
    done
    echo "Startup check timed out. Inspect: ./start-services.sh logs" >&2
    exit 1
}

setup() {
    require_root setup
    create_env
    install_dependencies
    configure_database
    configure_nginx
    start_processes
}

start() {
    require_root start
    configure_database
    configure_nginx
    start_processes
}

stop() {
    pm2 delete ca-ai-vllm ca-ai-backend ca-ai-frontend >/dev/null 2>&1 || true
    if command -v fuser >/dev/null 2>&1; then
        fuser -k 3001/tcp 8000/tcp 8001/tcp >/dev/null 2>&1 || true
    fi
    service nginx stop >/dev/null 2>&1 || true
    service mariadb stop >/dev/null 2>&1 || true
}

status() {
    load_env
    pm2 status || true
    printf "API:      "
    local_curl --fail --silent --max-time 5 http://127.0.0.1:8000/ || true
    printf "\nFrontend: "
    local_curl --silent --max-time 5 --output /dev/null --write-out '%{http_code}' http://127.0.0.1:3001/ || true
    printf "\nvLLM:     "
    if local_curl --fail --silent --max-time 5 http://127.0.0.1:8001/health >/dev/null; then
        echo ready
    else
        echo loading-or-failed
    fi
}

case "${1:-status}" in
    setup) setup ;;
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    logs)
        if [[ $# -gt 1 ]]; then pm2 logs "$2"; else pm2 logs; fi
        ;;
    *) echo "Usage: $0 {setup|start|stop|restart|status|logs [process]}" >&2; exit 2 ;;
esac
