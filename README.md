# Orchestra + Clover

Orchestra is an AI-powered project management system that turns a project idea into a dependency-locked engineering roadmap, auto-assigns tasks to team members based on skill profiles, and tracks progress across GitHub and Discord. Clover is the conversational assistant that answers natural-language questions about your project using RAG search and a Neo4j knowledge graph.

## What it does

1. **Blueprint generation** — describe your project, provide your tech stack and team members, and Orchestra generates a full task roadmap with priorities, deadlines, dependencies, and assignments using Gemini
2. **Smart assignment** — tasks are assigned based on each team member's skill profile, scoped only to the project team
3. **Knowledge graph** — tasks, developers, and skills are stored in Neo4j with relationships, powering dependency tracking and skill gap detection
4. **Clover** — ask questions like "what is blocked?" or "who is working on the API?" and get answers grounded in live task data and recent GitHub/Discord activity
5. **Activity tracking** — GitHub commits and Discord messages are ingested, normalized, and linked to roadmap tasks in real time

## Team

| Name | Role | GitHub |
|------|------|--------|
| Mitaali Singh | Lead · PM · AI Developer | @mitaalisingh |
| Naman Gupta | Knowledge Graph Engineer | @Naman-GG |
| Arnav Tripathi | Infrastructure Engineer | @ArnavXT |
| Sarvagya Prakash | Data Pipeline Engineer | @SarvagyaPrakash |
| Prince Negi | Interactive Canvas Specialist | @PrinceNegi |
| Isha Mahadev | Interface Developer | @IshaMahadev |

## Repos

| Repo | Description |
|------|-------------|
| `orchestra-ai` | AI server — blueprint generation, task assignment, Clover assistant, knowledge graph, semantic search |
| `orchestra-backend` | Backend API — auth, event ingestion from GitHub and Discord, WebSocket feed, Postgres |
| `orchestra-frontend` | Web app — project creation, workflow canvas, kanban board, Clover chat, calendar |

## Architecture

```
User fills in project form (name, description, tech stack, members)
        |
        v
Frontend → Backend proxy → POST /blueprint (AI Server)
        |
        v
Gemini generates tasks with IDs, priorities, deadlines, dependencies, assignments, summary
        |
        ├── Tasks saved to Neo4j (knowledge graph)
        ├── Tasks saved to Postgres (via POST /tasks)
        └── Project saved to Postgres (via POST /projects)
        |
        v
Frontend displays workflow canvas (ReactFlow) + kanban board
        |
        v
GitHub/Discord events ingested by backend → linked to tasks by AI server
        |
        v
Clover answers questions using task data + graph + live events (RAG + Gemini)
```

**Security:** Frontend never calls the AI server directly. All AI server endpoints are protected by `INTERNAL_API_KEY` — the backend holds the key and proxies requests. This keeps the key out of the browser.

## API endpoints (AI Server)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/blueprint` | Generate roadmap from project details |
| POST | `/assign` | Assign tasks to team based on skills |
| POST | `/clover` | Ask a project question (RAG + Gemini) |
| GET | `/tasks` | Get all tasks from Neo4j |
| GET | `/graph` | Get knowledge graph (ReactFlow format) |
| GET | `/search` | Semantic task search |
| GET | `/standup` | Generate per-person standup messages |
| GET | `/replan` | Suggest reassignment for blocked tasks |
| GET | `/skill-gap` | Detect tasks with no skilled assignee |
| POST | `/onboarding` | Infer skills from GitHub and add developer to graph |
| POST | `/commit-intel` | Link GitHub/Discord events to roadmap tasks |
| GET | `/team` | Get all team members and skills |
| POST | `/team/manual` | Manually set a developer's skills |

## Live URLs

| Service | URL |
|---------|-----|
| AI Server | https://orchestra-ai-36zm.onrender.com |
| Backend | https://orchestra-backend-30fy.onrender.com |
| API Docs | https://orchestra-ai-36zm.onrender.com/docs |

## Stack

Python · FastAPI · Gemini API · Neo4j · ChromaDB · PostgreSQL · React · ReactFlow · Render
