# Root Dockerfile so `gcloud run deploy --source .` builds the REMOTE pharmacy
# MCP server with a single command (requirement #6). Identical build to
# deploy/Dockerfile; kept at the repo root because Cloud Run's --source looks
# for a Dockerfile here.
#
# The image only contains the server; the MCP protocol is hand-written in
# src/servers/pharmacy/core.py (no MCP SDK).

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Server-only dependencies (no LLM SDK needed on the server).
COPY deploy/requirements-server.txt ./requirements-server.txt
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy the pharmacy server source.
COPY src/servers/pharmacy ./pharmacy

# Cloud Run injects the port via $PORT.
ENV PORT=8080
EXPOSE 8080

# Optional: set PHARMACY_API_KEY at deploy time to require the X-API-Key header.
# ENV PHARMACY_API_KEY=change-me

WORKDIR /app/pharmacy
CMD ["python", "server_http.py"]
