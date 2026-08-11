# Orchestra - Project Context for Codex

## What is this project?
Orchestra is an AI-powered project manager for small teams and hackathon participants.
It breaks down app ideas into structured task graphs, tracks who is working on what,
and integrates across GitHub, Figma, and Discord.

## My Role
I am Member 2 - Knowledge Graph Engineer.
Responsibilities: Neo4j schema, database connection drivers, vector database embeddings, query traversal.

## Current Stage
Late-stage. The AI/graph service is fully built and deployed (see Deployment). Focus has
moved from initial ingestion to the query/endpoint layer, Clover graph integration, and
aligning the graph with the backend as the source of truth for tasks.

## My Current Focus
- Maintain the Neo4j query + endpoint layer (`/tasks`, `/graph`, `/team`, `/team/manual`, ...).
- Keep Clover's graph context working (it now reads the graph in-process, not over HTTP).
- Resolve the task source-of-truth mismatch with the backend: the backend's Postgres uses
  `task_NNN` ids, the graph uses `T1`-style ids — these must be aligned before the status
  backfill (`backfill.py`) can run.

## Data & Source of Truth
The old JSON files (blueprint.json / assigned.json / skills.json) are NO LONGER in the repo.
Data now lives in databases:
- **Neo4j (Aura)** — the task / developer / skill graph; source of truth for the AI service.
- **Neon Postgres** — owned by the backend (users, auth, events, and increasingly tasks).

Key modules: `ingest.py` (push tasks/skills into Neo4j), `query.py` / `graph_query.py` /
`relationship_queries.py` (read + traverse), `blueprint.py` / `assign.py` (Gemini generation),
`clover.py` (RAG assistant), `main.py` (the FastAPI app).

## Graph Schema
Three node types:
  - Task       (id, title, track, description, status, assigned_to, created_at, updated_at)
  - Developer  (name)
  - Skill      (name)

Three relationship types:
  - (Task)-[:DEPENDS_ON]->(Task)
  - (Developer)-[:ASSIGNED_TO]->(Task)
  - (Developer)-[:HAS_SKILL]->(Skill)

## Tech Stack
- Python + FastAPI (served with uvicorn) — the AI/graph API (`main.py`)
- Neo4j (Aura) via the neo4j Python driver — the knowledge graph
- ChromaDB — vector embeddings for semantic search / Clover RAG
- google-genai (Gemini) — blueprint generation, assignment, Clover, embeddings
- python-dotenv for credentials

## Environment / Credentials
Stored in `.env` (not committed; see `.env.example`):
  NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE
  GEMINI_API_KEY     — used by the Gemini-backed endpoints
  INTERNAL_API_KEY   — the x-api-key guarding write / sensitive endpoints
GOTCHA: on current Aura instances NEO4J_USERNAME and NEO4J_DATABASE are the
instance ID (e.g. `74a94ebe`), NOT "neo4j".

## Deployment
- This AI/graph service is deployed on **Render**: https://orchestra-ai-36zm.onrender.com
  (free tier — sleeps after ~15min idle, ~30-50s cold start). Procfile runs `uvicorn main:app`.
- The **backend** is a SEPARATE service/repo (OAuth, webhooks, events, Postgres) on its own
  Render deployment (paid tier). The AI service calls its `/events`. Its URL has moved
  accounts several times — confirm the current one before using it.
- Write / sensitive endpoints require the `x-api-key` header (value = INTERNAL_API_KEY,
  which has been rotated — do not assume old values).

## Team Members
- Member 1 (Mitaali)   - Agent Architect: LLM prompting, JSON extraction, blueprint.py, assign.py
- Member 2 (Naman)     - Knowledge Graph Engineer: Neo4j schema, ingestion, vector embeddings (that's me)
- Member 3 (Arnav)     - Infrastructure Engineer: backend server, OAuth, webhooks
- Member 4 (Sarvyagya) - Data Pipeline Engineer: semantic data cleaner, state machine
- Member 5 (Prince)    - Interactive Canvas Specialist: reactflow graph UI
- Member 6 (Isha)      - Interface Developer: dashboard shell, chat components

## What Codex Should Help With Right Now
1. Maintain/debug the FastAPI endpoints and the Neo4j query layer
2. Keep the graph and Clover correct and in sync
3. Align the graph with the backend as the task source of truth (ids, statuses)
4. Verify changes locally where possible, then push to GitHub (orchestra-A/orchestra-ai)
   (note: chromadb + google-genai are deploy-only deps; importing the full app needs them)

## 6-Week Timeline Reference
- Week 1: Sandbox — practiced Neo4j with 3-node mock graph ✓ DONE
- Week 2-3: Build ingestion layer, inject AI task lists into Neo4j ✓ DONE
- Week 4: Git-driven automation, skill profile mapping ✓ DONE
- Week 5: Graph-RAG + vector embeddings + Clover AI chatbot ✓ DONE
- Week 6: System hardening, end-to-end integration & deployment ← CURRENT
