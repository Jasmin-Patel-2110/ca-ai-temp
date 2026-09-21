# CA AI Tool

Invoice extraction application: Next.js frontend, FastAPI backend, MariaDB, ChromaDB, and Qwen3-VL served by vLLM.

## One-day Runpod demo deployment

Docker image remains generic Runpod template. Clone this repository once into persistent `/workspace`, then run repository setup script. Do not place GitHub Personal Access Token in Dockerfile, image, clone URL, or committed files.

### Runpod template

- GPU: L40S 48 GB recommended. RTX 4090, L40, Ada 6000, or H100 also support FP8.
- Network volume: at least 80 GB mounted at `/workspace`. Model cache, Python environment, MariaDB, and ChromaDB live there.
- Exposed HTTP port: `3000` only. Ports `3306`, `8000`, and `8001` remain internal.
- Container disk: 20 GB or more.

For a 24 GB GPU, edit `.env.runpod` after setup and use:

```dotenv
VLLM_MAX_MODEL_LEN=16384
VLLM_MAX_NUM_SEQS=2
VLLM_MAX_PIXELS=301056
VLLM_MAX_OUTPUT_TOKENS=4096
```

Then run `./start-services.sh restart`.

### Clone private repository

Open Runpod terminal. Git prompts keep token out of shell history:

```bash
cd /workspace
git clone https://github.com/kriit-techadmin/CA-AI-Tool.git
# Username: GitHub username
# Password: fine-grained Personal Access Token with read access to this repository
cd CA-AI-Tool
chmod +x start-services.sh
```

Prefer fine-grained, read-only, short-lived token. Revoke it after clone. SSH deploy key is safer for later CI/CD.

### Install and start

```bash
./start-services.sh setup
```

Setup performs these one-time operations:

1. Creates `/workspace/venvs/ca-ai` with current vLLM and backend dependencies.
2. Builds Next.js frontend.
3. Generates `.env.runpod` with random JWT and MariaDB secrets.
4. Initializes persistent MariaDB, ChromaDB, and local document storage under `/workspace/ca-ai-data`.
5. Configures Nginx on public port `3000`.
6. Starts frontend, backend, and vLLM under PM2.

Model `Qwen/Qwen3-VL-8B-Thinking-FP8` downloads on first start. Application and API become available before model finishes loading.

### Check and operate

```bash
./start-services.sh status
./start-services.sh logs ca-ai-vllm
./start-services.sh logs ca-ai-backend
./start-services.sh restart
./start-services.sh stop
```

Open Runpod proxy URL for HTTP port `3000`. Nginx routes browser API calls to FastAPI and all other traffic to Next.js. After a pod/container restart, rerun `./start-services.sh start`.

### Optional configuration

Edit `.env.runpod` before restart:

- `HF_TOKEN`: optional Hugging Face token for higher download limits.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`: optional. Without a bucket, documents persist locally under `/workspace/ca-ai-data/documents`.
- `INVOICE_BOOK_COMPANY_NAME`: company used to classify invoices as sales or purchases.
- `CORS_ORIGINS`: comma-separated origins only when frontend and API use different public origins. Same-origin Runpod deployment leaves it empty.

Never expose vLLM, MariaDB, or FastAPI ports publicly for this layout.
