# wipro-assignment-varsha

Multi-agent **loan risk assessment** service. A **LangGraph** orchestration runs specialized agents (intake, verification, risk, negotiation, and others) with **Groq** LLM calls. The API is a **Flask** app with Pydantic validation, rate limits, structured logging, and an **`api_log`** database table for request auditing and debugging.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI (Jinja template) |
| `POST` | `/assess` | Run the assessment graph on a JSON or form payload |
| `GET` | `/healthz` | Liveness (Docker `HEALTHCHECK` and load balancers) |

## Requirements

- **Python 3.11+**
- A **GROQ_API_KEY** (see [Groq Console](https://console.groq.com/)) for model calls
- A database URL for `api_log` (default: SQLite; set `DATABASE_URL` for production)

## Configuration

Copy `.env.example` to `.env` and set at least `GROQ_API_KEY`. Other variables are documented in `.env.example` (CORS, rate limits, log level, port, Groq model and timeouts).

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
```

Run the app (after activating the venv and loading `.env`):

- Simplest: `python app.py` (uses `PORT` from the environment; default `8080`)
- Or with the Flask CLI: set `FLASK_APP=app.py` (or `export` / `$env:`) and run `flask run --port 8080`

For production-style serving:

```bash
gunicorn --bind 0.0.0.0:8080 app:app
```

## Quality checks

Tooling is defined in `pyproject.toml` (Black, isort, Ruff, Mypy, Pytest, coverage). The Cloud Build pipeline runs `ruff` and `pytest` with coverage; align local checks with that file.

## Docker

Build and run (maps host port 8080):

```bash
docker build -t loan-risk-multiagent .
docker run --rm -p 8080:8080 -e GROQ_API_KEY=your_key_here loan-risk-multiagent
```

## Deployment (Google Cloud)

The pipeline in `cloudbuild.yaml` runs **Ruff**, **Pytest** (with coverage), then **Docker build/push** to **Artifact Registry** and **`gcloud run deploy`** to **Cloud Run**.

**This repository is wired to:**

| Setting | Value |
|---------|--------|
| GCP project (display name) | My First Project |
| Project number | `278595266473` |
| Project ID | `project-c578a9e8-e300-4241-b6d` |
| Region | `us-central1` |
| Artifact Registry repository | `app` |
| Cloud Run service | `loan-risk-multiagent` |
| Image (pattern) | `us-central1-docker.pkg.dev/project-c578a9e8-e300-4241-b6d/app/loan-risk-multiagent:TAG` |
| Groq key at deploy | **Secret Manager** secret `GROQ_API_KEY` (mounted as env `GROQ_API_KEY` on Cloud Run) |
| Build identity | `projects/project-c578a9e8-e300-4241-b6d/serviceAccounts/278595266473-compute@developer.gserviceaccount.com` |

**One-time IAM** for that build service account (as noted in `cloudbuild.yaml`): `logging.logWriter`, `iam.serviceAccountUser` (on itself), `run.admin`, `artifactregistry.writer`, `secretmanager.secretAccessor` (for `GROQ_API_KEY`).

**Trigger a build** from a connected repo in Cloud Build, or from a machine with `gcloud` configured: run Cloud Build on this config so `SHORT_SHA` and substitutions apply (see [Cloud Build](https://cloud.google.com/build/docs) for the exact `gcloud builds submit` invocation you prefer).

If you fork or reuse this in another project, change the `substitutions` and `serviceAccount` in `cloudbuild.yaml` to match the new project.

## Project layout (high level)

- `app.py` — Flask routes and API logging
- `agents/` — Graph nodes and LLM tools
- `config.py` — Pydantic settings
- `db.py` / `models.py` — SQLAlchemy and `api_log` model
- `schemas.py` — Request/response Pydantic models
- `tests/` — Pytest suite
