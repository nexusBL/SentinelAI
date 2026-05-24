# SentinelAI Local Production Deployment

This guide explains the Phase 12 deployment foundation. It runs SentinelAI locally with a production-style shape while staying beginner-friendly and laptop-safe.

## Architecture

```mermaid
flowchart LR
    Browser[Browser] --> Nginx[NGINX Reverse Proxy]
    Nginx --> App[FastAPI + Gunicorn + Uvicorn Workers]
    App --> Artifacts[(artifacts volume)]
    App --> Memory[(memory_store volume)]
    App --> Ollama[Host Ollama Service]
```

The Docker stack contains:

| Service | Purpose |
|---|---|
| `sentinelai-app` | FastAPI dashboard/backend served by Gunicorn with Uvicorn workers |
| `sentinelai-nginx` | Reverse proxy that exposes the app at `http://127.0.0.1:8000` |
| `sentinelai_artifacts` | Named Docker volume for run reports, screenshots, traces, and metrics |
| `sentinelai_memory_store` | Named Docker volume for FAISS memory data |

## Prerequisites

You already verified Docker is installed:

```powershell
docker --version
docker compose version
```

For AI-backed Phase 3 through Phase 6 runs, install Ollama on the host and start it separately:

```bash
ollama serve
ollama pull llama3
```

The compose stack points to host Ollama with:

```text
http://host.docker.internal:11434/api/generate
```

## Start The Stack

From the repository root:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

Open:

```text
http://127.0.0.1:8000
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Stop The Stack

```powershell
docker compose -f docker/docker-compose.yml down
```

To remove persistent named volumes as well:

```powershell
docker compose -f docker/docker-compose.yml down -v
```

## Logs

Follow all service logs:

```powershell
docker compose -f docker/docker-compose.yml logs -f
```

App logs only:

```powershell
docker compose -f docker/docker-compose.yml logs -f app
```

NGINX logs only:

```powershell
docker compose -f docker/docker-compose.yml logs -f nginx
```

## Persistent Storage

The app writes generated data into Docker named volumes:

- `/app/artifacts` stores `artifacts/runs/<run_id>/`
- `/app/memory_store` stores FAISS memory data

These volumes survive container restarts and rebuilds. They are intentionally separate from the source tree so deployment runs do not dirty the Git worktree.

## Environment Configuration

Most runtime settings come from environment variables. Important deployment values:

| Variable | Default In Compose | Purpose |
|---|---|---|
| `SENTINELAI_ARTIFACTS_DIR` | `/app/artifacts` | Run artifact storage |
| `SENTINELAI_MEMORY_VECTOR_DB_PATH` | `/app/memory_store` | Persistent memory path |
| `SENTINELAI_OLLAMA_ENDPOINT` | `http://host.docker.internal:11434/api/generate` | Host Ollama API |
| `SENTINELAI_BROWSER_HEADLESS` | `true` | Headless browser automation |
| `SENTINELAI_MCP_ENABLED` | `true` | MCP tool layer |

See [.env.example](../.env.example) for the broader runtime settings.

## Dependency Profile

The Docker image installs from `requirements-docker.txt`, which is intentionally smaller than the local development `requirements.txt`.

The app image uses the official Playwright Python runtime image so Chromium and its OS libraries are already present. The deployment profile uses the default hashing embedding provider, so it does not install the optional `sentence-transformers` stack. Local development keeps the full dependency file for experimentation.

## Troubleshooting

### Dashboard Does Not Open

Check container status:

```powershell
docker compose -f docker/docker-compose.yml ps
```

Then inspect logs:

```powershell
docker compose -f docker/docker-compose.yml logs app nginx
```

### Port 8000 Is Already In Use

Stop the local development dashboard or change the NGINX port mapping in `docker/docker-compose.yml`:

```yaml
ports:
  - "8080:80"
```

Then open `http://127.0.0.1:8080`.

### Ollama Connection Fails

Make sure Ollama is running on the host:

```bash
ollama serve
```

For local Python usage, `localhost` is correct. For Docker Compose, use `host.docker.internal`.

### Browser Automation Fails In Docker

The image installs Playwright Chromium and system dependencies during build. Rebuild the image if Playwright dependencies were interrupted:

```powershell
docker compose -f docker/docker-compose.yml build --no-cache app
```

### Memory Looks Empty

The memory volume starts empty. Run a Phase 5 or Phase 6 workflow from the dashboard, then refresh the Memory page.
