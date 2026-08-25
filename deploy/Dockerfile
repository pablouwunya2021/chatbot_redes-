# Container image for the REMOTE pharmacy MCP server (requirement #6).
# Build context is the repository root:
#     docker build -f deploy/Dockerfile -t pharmacy-mcp .
#
# The image only contains the server (FastAPI/uvicorn as a plain HTTP host);
# the MCP protocol itself is hand-written in src/servers/pharmacy/core.py.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Server-only dependencies (no LLM SDK needed on the server).
COPY deploy/requirements-server.txt ./requirements-server.txt
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy the pharmacy server source.
COPY src/servers/pharmacy ./pharmacy

# Cloud Run (and most PaaS) inject the port via $PORT.
ENV PORT=8080
EXPOSE 8080

# Optional: set PHARMACY_API_KEY at deploy time to require the X-API-Key header.
# ENV PHARMACY_API_KEY=change-me

WORKDIR /app/pharmacy
CMD ["python", "server_http.py"]
