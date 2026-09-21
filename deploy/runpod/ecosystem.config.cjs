const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const venv = process.env.VENV_DIR || "/workspace/venvs/ca-ai";
const model = process.env.VLLM_MODEL || "Qwen/Qwen3-VL-8B-Thinking-FP8";
const vllmPort = process.env.VLLM_PORT || "8002";
const frontendPort = process.env.FRONTEND_PORT || "3002";
const runtimeEnv = { ...process.env, pmx: "false" };
delete runtimeEnv.io;
delete runtimeEnv.trace;

module.exports = {
  apps: [
    {
      name: "ca-ai-vllm",
      cwd: root,
      script: path.join(venv, "bin/vllm"),
      interpreter: "none",
      args: [
        "serve",
        model,
        "--host", "127.0.0.1",
        "--port", vllmPort,
        "--served-model-name", model,
        "--reasoning-parser", "qwen3",
        "--max-model-len", process.env.VLLM_MAX_MODEL_LEN || "32768",
        "--gpu-memory-utilization", process.env.VLLM_GPU_MEMORY_UTILIZATION || "0.90",
        "--max-num-seqs", process.env.VLLM_MAX_NUM_SEQS || "4",
        "--mm-processor-kwargs", JSON.stringify({
          max_pixels: Number(process.env.VLLM_MAX_PIXELS || "602112"),
        }),
      ],
      autorestart: true,
      restart_delay: 10000,
      max_restarts: 10,
      kill_timeout: 30000,
      env: runtimeEnv,
    },
    {
      name: "ca-ai-backend",
      cwd: path.join(root, "ai_invoice_api"),
      script: path.join(venv, "bin/uvicorn"),
      interpreter: "none",
      args: ["app.main:app", "--host", "127.0.0.1", "--port", "8000"],
      autorestart: true,
      restart_delay: 3000,
      kill_timeout: 10000,
      env: runtimeEnv,
    },
    {
      name: "ca-ai-frontend",
      cwd: path.join(root, "Frontend"),
      script: "npm",
      args: ["start", "--", "--hostname", "127.0.0.1", "--port", frontendPort],
      autorestart: true,
      restart_delay: 3000,
      kill_timeout: 10000,
      env: runtimeEnv,
    },
  ],
};
