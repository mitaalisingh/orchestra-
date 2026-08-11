# Orchestra — Week 2–3 Progress Report

**Repository:** `orchestra-A/orchestra-ai` (AI + Knowledge Graph service)
**Reporting period:** Week 2–3 (Graph Ingestion Layer + AI Agent Pipeline)
**Contributors:** Member 1 — Mitaali (Agent Architect) · Member 2 — Naman (Knowledge Graph Engineer)

---

## 1. Summary

Over Weeks 2–3 the AI service moved from standalone scripts and mock data to a
**live, deployed FastAPI service backed by a Neo4j knowledge graph.** The
AI-generated roadmap is now ingested into Neo4j as a connected task graph, every
API endpoint reads directly from the graph (no more JSON files), and a
conversational assistant (Clover) answers project questions over real data. The
service is deployed on Render and integrated with the frontend and backend teams
over HTTP.

**Live service:** `https://orchestra-ai-36zm.onrender.com` · interactive docs at `/docs`

---

## 2. Member 2 — Naman (Knowledge Graph Engineer)

**Focus:** Neo4j schema, ingestion, graph read/traversal layer, deployment.

### Graph schema & ingestion (`ingest.py`)
- Designed and implemented the **three-node, three-relationship** schema:
  - Nodes: `Task`, `Developer`, `Skill`
  - Relationships: `(Task)-[:DEPENDS_ON]->(Task)`, `(Developer)-[:ASSIGNED_TO]->(Task)`, `(Developer)-[:HAS_SKILL]->(Skill)`
- Idempotent ingestion using `MERGE` + **uniqueness constraints** on `Task.id`,
  `Developer.name`, `Skill.name`, so re-running never duplicates nodes/edges.
- Ingests the full AI-generated roadmap (30 connected tasks) with dependencies,
  assignments, and skill links in one pass.

### Graph read & traversal layer
- **`query.py`** — read-layer queries over the graph, including `get_all_tasks()`
  which serves the canonical task list (powers `GET /tasks`).
- **`graph_query.py`** — returns the graph as **ReactFlow-ready `{nodes, edges}`**
  for the frontend canvas (powers `GET /graph`).
- **`relationship_queries.py`** — six callable Neo4j traversal functions delivered
  for Clover integration:
  - `tasks_for_person(name)` — "what is X working on?"
  - `blocked_tasks()` — "what is blocked?"
  - `dependencies_of(task_id, recursive=False)` — upstream dependencies
  - `dependents_of(task_id, recursive=False)` — downstream impact / blast radius
  - `skills_of(name)` — "what skills does X have?"
  - `who_has_skill(skill)` — "who can do X?"
  - All case-insensitive, return clean JSON-serialisable data, verified against
    live Neo4j.

### Architecture & deployment
- Migrated the service deployment from Railway to **Render**; updated all
  integration URLs and environment configuration.
- Established Neo4j as the **single source of truth**: contributed to removing the
  fragile `assigned.json` / `skills.json` file reads so all endpoints query the
  graph directly.
- Maintained Neo4j Aura (cloud) connection drivers and credentials handling.

---

## 3. Member 1 — Mitaali (Agent Architect)

**Focus:** LLM prompting, JSON extraction, AI agents that generate and reason over
the roadmap.

### Core AI pipeline
- **`blueprint.py`** — turns a raw app idea into a structured task graph
  (id, title, track, description, dependencies) via Gemini, with robust JSON
  extraction.
- **`assign.py`** — assigns roadmap tasks to team members based on their skills.
- **`skills.py` / `skill_gap.py`** — collect developer skill profiles and detect
  gaps between assigned work and team capability.

### Intelligence & assistant features
- **`clover.py`** — Clover conversational assistant: hybrid **RAG + graph**
  pipeline combining ChromaDB semantic search, Neo4j graph context, and live
  events to answer natural-language project questions with real names and task IDs.
- **`search.py`** — semantic task search over the roadmap using ChromaDB embeddings.
- **`commit_intel.py`** — links live GitHub/Discord events to roadmap tasks and
  stores enriched activity for retrieval.
- **`standup.py`** — automated daily standup generator grouped by person/status.
- **`re_planner.py`** — suggests re-planning around blocked tasks (who can take
  over, downstream impact).
- **`onboarding.py`** — generates a developer profile by scanning GitHub repos and
  detecting skills.

---

## 4. Live API surface (deployed)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Service health check |
| GET | `/tasks` | All tasks from Neo4j (backend integration) |
| PATCH | `/tasks/{task_id}/status` | Update a task's status in Neo4j |
| GET | `/graph` | ReactFlow `{nodes, edges}` (frontend canvas) |
| POST | `/blueprint` | Generate task graph from an idea |
| POST | `/assign` | Assign tasks to team members |
| GET | `/search` | Semantic task search |
| POST | `/clover` | Ask Clover a project question |
| GET | `/standup` | Daily standup summary |
| GET | `/replan` | Re-planning suggestions for blockers |
| GET | `/commit-intel` | Live event → task linkage |
| POST | `/onboarding` | GitHub-based skill profiling |
| GET | `/team` · `/project` | Team and project metadata |

Hardening added during the period: API-key auth on sensitive endpoints, input
validation/limits, ephemeral ChromaDB (no disk writes), and a smoke-test suite
(`test_endpoints.py`).

---

## 5. Status vs. roadmap

| Original plan | Status |
|---------------|--------|
| Week 2–3: Build ingestion layer, inject AI task lists into Neo4j | ✅ **Complete** — graph is the live backing store |
| AI blueprint → assign → ingest pipeline | ✅ Complete and exposed via API |
| Clover assistant (originally Week 5) | ✅ Live ahead of schedule |
| Vector / semantic search (ChromaDB) | ✅ Live |

### In progress / next (Week 4)
- **Git-driven graph automation:** extend the schema with a `File` node and
  `(Task)-[:TOUCHES]->(File)` relationship, linking people → tasks → code files
  from live GitHub commit data. (Pending one upstream change: the backend
  webhook normalizer needs to forward per-commit file paths — already requested.)
- **Graph-query consolidation:** route re-planning/Clover logic through the shared
  `relationship_queries.py` traversal module.

---
