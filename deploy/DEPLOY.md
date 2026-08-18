# Deploying the remote pharmacy MCP server (Requirement #6)

The remote server is exactly the same code as the local one; only the
**transport** changes from stdio to HTTP. Once deployed, point the chatbot at
it by setting `PHARMACY_REMOTE_URL` in `.env` and running the chatbot with
`--remote`.

Below are two paths: **Google Cloud Run** (recommended, matches the PDF's
reference tutorial) and **local Docker** (useful for the Wireshark capture,
because traffic is plain HTTP).

---

## Option A — Google Cloud Run

Prerequisites: a Google Cloud account, the `gcloud` CLI installed and
authenticated, and a project with billing (Cloud Run has a generous free tier).

```bash
# 0. From the repository root. Set your project id.
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

# 1. Build & push the image with Cloud Build (uses deploy/Dockerfile).
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/pharmacy-mcp \
  --config /dev/stdin <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build','-f','deploy/Dockerfile','-t','gcr.io/$PROJECT_ID/pharmacy-mcp','.']
images: ['gcr.io/$PROJECT_ID/pharmacy-mcp']
EOF

# 2. Deploy to Cloud Run.
gcloud run deploy pharmacy-mcp \
  --image gcr.io/YOUR_PROJECT_ID/pharmacy-mcp \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars PHARMACY_API_KEY=demo-key

# 3. Cloud Run prints a Service URL, e.g.
#    https://pharmacy-mcp-xxxxxxxx-uc.a.run.app
#    The MCP endpoint is that URL + /mcp
```

If you prefer the one-shot form, this also works from the repo root:

```bash
gcloud run deploy pharmacy-mcp --source . --region us-central1 --allow-unauthenticated
```
(but `--source .` uses the repo's own build; keep `deploy/Dockerfile` as the
Dockerfile, or move it to the root before running.)

### Point the chatbot at the remote server

```bash
# .env
PHARMACY_REMOTE_URL=https://pharmacy-mcp-xxxxxxxx-uc.a.run.app/mcp
PHARMACY_API_KEY=demo-key
```

```bash
python src/host/cli.py --remote          # terminal
REMOTE_PHARMACY=1 python src/ui/web/app.py   # web
```

Verify quickly:

```bash
curl https://pharmacy-mcp-xxxxxxxx-uc.a.run.app/healthz
curl -X POST https://pharmacy-mcp-xxxxxxxx-uc.a.run.app/mcp \
  -H 'Content-Type: application/json' -H 'X-API-Key: demo-key' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

---

## Option B — Local Docker (plain HTTP, best for Wireshark)

Cloud Run terminates TLS, so a capture there is encrypted. For a **readable**
Wireshark capture, run the same container locally over plain HTTP:

```bash
docker build -f deploy/Dockerfile -t pharmacy-mcp .
docker run --rm -p 8000:8080 -e PHARMACY_API_KEY=demo-key pharmacy-mcp
# endpoint: http://127.0.0.1:8000/mcp
```

Then set `PHARMACY_REMOTE_URL=http://127.0.0.1:8000/mcp` and run the chatbot
with `--remote`. See `docs/wireshark/WIRESHARK_ANALYSIS.md` for the capture and
analysis procedure (requirement #7).

---

## Option C — Cloudflare (alternative mentioned in the PDF)

The same container runs on any platform that serves an HTTP port, including a
small VM behind Cloudflare, or Cloudflare Tunnel exposing the local container:

```bash
docker run --rm -p 8000:8080 pharmacy-mcp
cloudflared tunnel --url http://localhost:8000
# Cloudflare prints a public https URL; append /mcp for PHARMACY_REMOTE_URL.
```
