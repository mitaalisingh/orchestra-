# Orchestra — Reviewer Demo Script
*Knowledge Graph & AI Engineer track (Naman)*

## What you're proving
Orchestra turns a plain-English app idea into a **live, assigned task graph** that stays
in sync across a Neo4j knowledge graph and the backend's Postgres — and a Graph-RAG
assistant (Clover) answers questions over it. Your piece is the graph, the ingestion,
the dual-store alignment, the live status sync, and Clover.

## Setup (do 5 min before reviewers arrive)
The AI + backend are on Render's free tier and **cold-start ~40s after idle**. Warm them:
```bash
curl -s -o /dev/null -w '%{http_code}\n' https://orchestra-ai-36zm.onrender.com/tasks
curl -s -o /dev/null -w '%{http_code}\n' https://orchestra-backend-30fy.onrender.com/tasks
```
Both should print `200`. (The demo script also pre-warms, but do this first so the very
first click in front of reviewers is instant.)

Open in tabs: the **frontend** (https://orchestra-frontend-roan.vercel.app) and a
terminal in the repo. The frontend is wired to the live AI + backend.

---

## The 5-act flow (run `./demo.sh` and narrate each act)

**Act 1 — "This is the knowledge graph I designed."**
> "Three node types — Task, Developer, Skill — and three relationship types:
> DEPENDS_ON between tasks, ASSIGNED_TO from developers, HAS_SKILL for capabilities.
> Everything downstream reads from this."

**Act 2 — "Type an idea, get an assigned plan."**
> "I POST a project idea. Gemini breaks it into tasks; assignment is **scoped to the
> team roster** so no task lands on someone off the project. Every task is then written
> into Neo4j *and* pushed to the backend's Postgres."

**Act 3 — "Both stores are one source of truth."**
> "Here's the part that's easy to get wrong. The same task ids — T1, T2, … — exist in
> *both* Neo4j and Postgres. No translation layer, no drift. That alignment is what lets
> status flow between them."

**Act 4 — "Move a task in the backend, the graph follows — live."**
> "I mark T3 in-progress in the backend, the source of truth for status. Then I read T3
> straight out of Neo4j — it's already in-progress. No batch job, no manual sync. The
> graph reflects reality in real time."

**Act 5 — "Ask Clover, the Graph-RAG assistant."**
> "Clover doesn't just hit an LLM. It runs semantic search over the tasks, then walks the
> knowledge graph — dependencies, assignees, skills — and feeds that structured context
> to Gemini. So it answers *who* owns *what* and *what's blocked* with real relationships,
> not guesses."

---

## Optional: the visual version (frontend)
If you want the "wow", drive Act 2 + Act 5 through the frontend instead of curl:
- Enter the idea in the UI → watch the ReactFlow graph render the dependency DAG.
- Open the Clover chat panel → ask the same question.
Keep the terminal handy to *prove* what the UI is showing (Acts 3 & 4).

## If something goes wrong
- **Blank / slow first call:** cold start. Wait 40s, retry. (You pre-warmed, so unlikely.)
- **A Gemini act errors:** the key can rotate — the graph/sync acts (1,3,4) don't need
  Gemini and still land the core story. Fall back to those.
- **Graph looks empty:** Neo4j Aura free tier pauses after ~3 days idle — resume it in the
  Aura console before the demo.

## One-liner if you only get 30 seconds
> "Orchestra takes an app idea, uses an LLM to generate an assigned task graph, stores it
> in a Neo4j knowledge graph that stays id-aligned and status-synced with the backend
> Postgres, and a Graph-RAG assistant answers questions by walking that graph."
