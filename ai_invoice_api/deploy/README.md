# Deploy Invoice API behind Nginx (EC2 Ubuntu)

Use these steps on your EC2 instance (app path: `/home/ubuntu/invoice_ai/invoice_api`).

## 1. Copy deploy files to EC2

From your **Windows** machine (project root: `d:\Sahaj_Work_place\ai_invocie\invoice_api`), create `deploy` on EC2 then copy:

```powershell
# One-time: create deploy folder on EC2 (run in PowerShell or use same SSH key)
# ssh -i "C:\Users\sahaj\Downloads\AutomatedCATool.pem" ubuntu@<EC2-PUBLIC-IP> "mkdir -p /home/ubuntu/invoice_ai/invoice_api/deploy"

$KEY = "C:\Users\sahaj\Downloads\AutomatedCATool.pem"
$REMOTE = "ubuntu@<EC2-PUBLIC-IP>:/home/ubuntu/invoice_ai/invoice_api"
scp -i $KEY deploy/invoice-api.service "${REMOTE}/deploy/"
scp -i $KEY deploy/invoice-api.nginx "${REMOTE}/deploy/"
```

Replace `<EC2-PUBLIC-IP>` with your instance’s public IP or hostname.

---

## 2. On EC2: Python venv (if not already)

```bash
cd /home/ubuntu/invoice_ai/invoice_api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

If you don’t use a venv, edit the service file and set `ExecStart` to your `uvicorn` path (e.g. `/home/ubuntu/.local/bin/uvicorn`).

---

## 3. On EC2: Install and enable systemd service

```bash
sudo cp /home/ubuntu/invoice_ai/invoice_api/deploy/invoice-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable invoice-api
sudo systemctl start invoice-api
sudo systemctl status invoice-api
```

If `.env` is not in `/home/ubuntu/invoice_ai/invoice_api/`, create it or remove the `EnvironmentFile=` line from the service and set env vars another way.

---

## 4. On EC2: Install Nginx and enable site

```bash
sudo apt update && sudo apt install -y nginx
sudo cp /home/ubuntu/invoice_ai/invoice_api/deploy/invoice-api.nginx /etc/nginx/sites-available/invoice-api
sudo ln -sf /etc/nginx/sites-available/invoice-api /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable nginx
```

---

## 5. Open ports and test

- **Security group**: allow inbound **8080** (Nginx listens on 8080; use **80** and **443** if you change the config back to port 80 / add HTTPS).
- From your machine:

  ```bash
  curl http://<EC2-PUBLIC-IP>:8080/
  ```

  You should get the API health response.

---

## Optional: HTTPS with Let’s Encrypt

1. Point a domain (e.g. `api.yourdomain.com`) to the EC2 public IP (A record).
2. On EC2:

   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d api.yourdomain.com
   ```

3. Certbot will update the Nginx config and set up renewal.

---

## Optional: Expose Nginx via ngrok

Run ngrok on the **EC2 server** so the API is reachable at an ngrok URL (e.g. `https://xxxx.ngrok-free.app`) instead of `http://<EC2-IP>:8080`. Useful when your frontend (e.g. LedgerAI on another ngrok URL) needs to call the API.

**Flow:** `Internet → ngrok → EC2:8080 (Nginx) → EC2:8000 (FastAPI)`

### 1. Install ngrok on EC2

```bash
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install -y ngrok
```

### 2. Add your auth token

Sign up at [ngrok.com](https://ngrok.com), get your token from the dashboard, then:

```bash
ngrok config add-authtoken <YOUR_NGROK_TOKEN>
```

### 3. Start the tunnel to Nginx (port 8080)

```bash
ngrok http 8080
```

Leave this running. You will see something like `Forwarding  https://xxxx.ngrok-free.app -> http://localhost:8080`. Use that **HTTPS** URL as your API base URL in the frontend (e.g. in LedgerAI env or `{{url}}`).

### 4. CORS

Your API already allows the frontend origin. If you use a new ngrok URL for the API, add it to `allow_origins` in `app/main.py` only if the browser sends that origin (usually the frontend origin is what matters).

---

## Cost & speed (g6.xlarge 24GB)

**Current setup:** Speed optimizations are tuned for g6.xlarge:
- Image resize: 1120px (via `EXTRACT_PDF_MAX_PX`)
- Token limits: 2048 (via `OLLAMA_NUM_PREDICT`, `OLLAMA_NUM_CTX`)

**Lower cost options:**
- **g4dn.xlarge** (~$0.53/hr): T4 16GB – enough for qwen2.5vl:7b, ~35% cheaper than g6
- **Spot instances**: 60–70% savings – use Spot for g4dn or g6
- **glm-ocr** model: ~0.9B, very fast – could run on **g4dn.xlarge** or even smaller

**Faster (more speed):** Set in `.env`:
```
EXTRACT_PDF_MAX_PX=960
OLLAMA_NUM_PREDICT=1024
```

---

## Useful commands

| Action | Command |
|--------|--------|
| API logs | `sudo journalctl -u invoice-api -f` |
| Restart API | `sudo systemctl restart invoice-api` |
| Nginx test | `sudo nginx -t` |
| Reload Nginx | `sudo systemctl reload nginx` |
