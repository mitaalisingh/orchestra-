"""Clover — conversational project assistant powered by RAG + Gemini."""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

from commit_intel import fetch_live_events
from graph_query import build_reactflow_graph
from query import get_all_tasks, patch_task_status
from search import ensure_indexed, get_embedding

MODEL_NAME = "gemini-2.5-flash-lite"

# Sentinel so ask_clover can tell "caller pre-fetched this (possibly None)" apart
# from "caller didn't pass it, fetch it yourself". fetch_graph()/fetch_live_events()
# can both legitimately return None, so a plain None default wouldn't distinguish.
_UNSET = object()

SYSTEM_PROMPT = """You are Clover, an AI project assistant for a software development team. You have access to three sources of context:
1. Task context — structured task data with IDs, titles, assignees, tracks, and statuses
2. Graph context — knowledge graph showing relationships between people, tasks, and skills
3. Recent activity context — live Discord and GitHub events showing what the team has been doing

Use these rules to answer questions:
- "What did X work on recently?" or "What has X been doing?" → prioritise recent activity context
- "Who is working on X?" or "Who owns X?" → prioritise task context and graph context
- "What tasks are blocked?" or "What is blocked?" → prioritise task context, look for blocked status or unmet dependencies
- "What skills does X have?" or "Who can do X?" → prioritise graph context and task context
- For all other questions → use whichever context is most relevant

Always be specific — mention actual names, task IDs, titles, and timestamps in your answers. When a task has a "project" field, cite the project name alongside the task id, e.g. "Implement 'How to Use' UI (calculator app - Pb251a963-T14)". If the context does not contain enough information to answer, say so clearly.

Formatting rules — strictly follow these:
- Write in plain conversational text only. No markdown, no asterisks, no bold, no bullet symbols, no headers.
- Use plain dashes (-) for lists if needed, nothing else.
- Keep responses concise — 3 to 6 sentences unless the question genuinely needs more detail."""


# Fetches a {project_id: project_name} map from the backend (best-effort).
def fetch_project_names() -> dict[str, str]:
    """Return {project_id: name} from the backend, or {} on any failure.

    The graph only stores the project id (embedded in each task id, e.g.
    "P4a584a19-T3"); the human-readable name lives in the backend's projects
    table. We pull it so Clover can cite "PantryPal" instead of a bare id.
    """
    backend_url = os.getenv("BACKEND_URL", "https://orchestra-backend-30fy.onrender.com")
    try:
        resp = requests.get(f"{backend_url}/projects", timeout=30)
        resp.raise_for_status()
        projects = resp.json().get("projects", [])
        return {p["id"]: p.get("name", "") for p in projects if p.get("id")}
    except Exception:
        return {}


# Resolves a task id to its project name using the id prefix (e.g. "P4a..-T3").
def project_name_for_task(task_id: str, name_map: dict[str, str]) -> str:
    """Return the project name whose id prefixes this task id, else ""."""
    if not task_id or not name_map:
        return ""
    for pid, pname in name_map.items():
        if pid and (task_id == pid or task_id.startswith(f"{pid}-")):
            return pname
    return ""


# Finds the 3 tasks that best match the user's question using semantic search.
def search_top_tasks(question: str, api_key: str, project_id: str | None = None) -> list[dict]:
    """Find the 3 most relevant tasks using the shared, cached ChromaDB index."""
    tasks = get_all_tasks()
    if not tasks:
        return []

    embed_client = genai.Client(api_key=api_key)
    # Reuse the shared index (embeds every task once, cached across requests)
    # rather than re-embedding on every call. Scope to the project at query time
    # via a metadata filter instead of indexing a per-project subset.
    collection = ensure_indexed(embed_client, tasks)

    query_embedding = get_embedding(embed_client, question)
    query_kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": 3,
        "include": ["metadatas", "distances"],
    }
    if project_id:
        query_kwargs["where"] = {"project_id": project_id}
    results = collection.query(**query_kwargs)

    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    matches: list[dict] = []
    for i, metadata in enumerate(metadatas):
        distance = distances[i] if i < len(distances) else None
        matches.append({**metadata, "distance": distance})

    return matches


# Builds the project knowledge graph directly from Neo4j (in-process).
def fetch_graph() -> dict | None:
    """Build the project graph in-process from Neo4j. Returns None on failure.

    Calls build_reactflow_graph() directly instead of doing an HTTP round-trip
    to our own /graph endpoint: that self-call carries no x-api-key, so the auth
    guard returns 401 and the graph context silently goes missing. In-process is
    also faster and needs no network. Same {nodes, edges} shape either way.
    """
    try:
        return build_reactflow_graph()
    except Exception:
        return None


# Checks if a graph node is related to the question by name or assignee.
def is_relevant_node(node: dict, question: str) -> bool:
    """Return True if a graph node matches the question by title or assignee."""
    q = question.lower()
    data = node.get("data", {})
    label = str(data.get("label", "")).lower()
    assigned_to = str(data.get("assigned_to", "")).lower()

    if assigned_to and assigned_to in q:
        return True
    if label and label in q:
        return True
    for word in q.split():
        if len(word) > 2 and word in label:
            return True
    return False


# Fetches the graph and keeps only the nodes and edges that match the question.
def get_relevant_graph_context(question: str, graph: dict | None) -> dict | None:
    """Fetch and filter graph nodes/edges relevant to the question."""
    if not graph:
        return None

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    relevant_nodes = [node for node in nodes if is_relevant_node(node, question)]

    if not relevant_nodes:
        return {"nodes": [], "edges": []}

    relevant_ids = {node["id"] for node in relevant_nodes}
    relevant_edges = [
        edge
        for edge in edges
        if edge.get("source") in relevant_ids or edge.get("target") in relevant_ids
    ]

    return {"nodes": relevant_nodes, "edges": relevant_edges}


# Builds relationship details for matched tasks using the full project graph.
def enrich_with_graph(task_ids: list[str], graph: dict) -> list[dict]:
    """Enrich task IDs with dependencies, assignees, and dependents from the graph."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    nodes_by_id = {node["id"]: node for node in nodes}

    enriched: list[dict] = []
    for task_id in task_ids:
        task_node = nodes_by_id.get(task_id)
        if not task_node:
            continue

        dependencies: list[dict] = []
        dependents: list[dict] = []
        assigned_to = None

        for edge in edges:
            if edge.get("source") != task_id and edge.get("target") != task_id:
                continue

            relationship = edge.get("data", {}).get("relationship", "")
            source = edge.get("source")
            target = edge.get("target")

            if source == task_id and relationship == "DEPENDS_ON":
                dep_node = nodes_by_id.get(target)
                if dep_node:
                    dependencies.append(dep_node)
            elif target == task_id and relationship == "DEPENDS_ON":
                dependent_node = nodes_by_id.get(source)
                if dependent_node:
                    dependents.append(dependent_node)
            elif target == task_id and relationship == "ASSIGNED_TO":
                developer_node = nodes_by_id.get(source)
                if developer_node:
                    assigned_to = developer_node

        enriched.append(
            {
                "task": task_node,
                "dependencies": dependencies,
                "assigned_to": assigned_to,
                "dependents": dependents,
            }
        )

    return enriched


# Builds the ordered prompt sections from all pre-fetched context sources.
def _build_prompt_parts(
    question: str,
    task_context: list[dict],
    conversation_history: list[dict] | None,
    live_events,
    full_graph,
    project_id: str | None = None,
    project_names: dict[str, str] | None = None,
) -> list[str]:
    """Shared prompt builder used by both ask_clover and stream_answer."""
    if project_id and full_graph:
        project_task_ids = {t.get("id") for t in get_all_tasks() if t.get("project_id") == project_id}
        full_graph["nodes"] = [n for n in full_graph.get("nodes", []) if n.get("id") in project_task_ids or n.get("type") == "developer"]
        full_graph["edges"] = [e for e in full_graph.get("edges", []) if e.get("source") in project_task_ids or e.get("target") in project_task_ids]

    # Tag each task with its project name so Gemini can cite it (the graph only
    # carries the project id, embedded in the task id). Best-effort — an empty
    # map just means tasks are cited by id alone, as before.
    name_map = fetch_project_names() if project_names is None else project_names
    tagged_context = []
    for task in task_context:
        pname = project_name_for_task(str(task.get("id", "")), name_map)
        tagged_context.append({**task, "project": pname} if pname else task)

    context_json = json.dumps(tagged_context, indent=2, ensure_ascii=False)
    prompt_parts = [f"Task context:\n{context_json}"]

    if conversation_history:
        history_text = "Conversation history (most recent last):\n"
        for item in conversation_history[-5:]:
            if not isinstance(item, dict):
                continue
            # Be tolerant of the client's history shape. Our own is
            # {question, answer}, but chat UIs often send {role, content} or
            # {sender, text} bubbles (incl. an opening greeting with no
            # question). Never index a key directly — a missing key used to
            # raise KeyError and turn the whole request into a 500.
            q = str(item.get("question") or "")
            a = str(item.get("answer") or "")
            if not q and not a:
                content = str(item.get("content") or item.get("text") or item.get("message") or "")
                if not content:
                    continue
                role = str(item.get("role") or item.get("sender") or "").lower()
                if role in ("user", "human"):
                    q = content
                else:
                    a = content
            history_text += f"User: {q}\nClover: {a}\n"
        history_text += (
            "\nIf the current question refers back to this conversation "
            '(e.g. "those changes", "that task", "they"), resolve the reference '
            "using the exchanges above."
        )
        prompt_parts.append(history_text)

    if live_events:
        commit_json = json.dumps(live_events, indent=2, ensure_ascii=False)
        prompt_parts.append(f"Recent activity context:\n{commit_json}")

    graph_context = get_relevant_graph_context(question, full_graph)
    if graph_context is not None:
        graph_json = json.dumps(graph_context, indent=2, ensure_ascii=False)
        prompt_parts.append(f"Graph context:\n{graph_json}")

    task_ids = [t.get("id") for t in task_context if t.get("id")]
    if full_graph:
        enriched = enrich_with_graph(task_ids, full_graph)
        if enriched:
            enriched_json = json.dumps(enriched, indent=2, ensure_ascii=False)
            prompt_parts.append(
                "Enriched graph context (relationships for matched tasks):\n"
                f"{enriched_json}"
            )

    prompt_parts.append(f"User question: {question}")
    return prompt_parts


# Sends all context to Gemini and returns Clover's answer as text.
def ask_clover(
    question: str,
    task_context: list[dict],
    api_key: str,
    conversation_history: list[dict] = None,
    project_id: str | None = None,
    graph=_UNSET,
    live_events=_UNSET,
    project_names: dict[str, str] | None = None,
) -> str:
    """Send retrieved tasks and graph context to Gemini and return an answer.

    `graph` and `live_events` may be passed in pre-fetched (see answer_question,
    which retrieves them in parallel with the semantic search). When left unset,
    they're fetched here so the CLI / direct callers keep working unchanged.
    `project_names` is the {id: name} map for citing project names (fetched in
    _build_prompt_parts when None).
    """
    full_graph = fetch_graph() if graph is _UNSET else graph
    if live_events is _UNSET:
        try:
            live_events = fetch_live_events()
        except Exception:
            live_events = None

    client = genai.Client(api_key=api_key)
    prompt_parts = _build_prompt_parts(
        question, task_context, conversation_history, live_events, full_graph,
        project_id, project_names,
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="\n\n".join(prompt_parts),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
        ),
    )

    return (response.text or "").strip()


# Yields Gemini response chunks as they're generated, then a final history event.
def stream_answer(
    question: str,
    api_key: str,
    conversation_history: list[dict] = None,
    project_id: str | None = None,
):
    """Retrieve context in parallel, then stream Gemini's answer chunk by chunk.

    Each yielded value is a JSON string in one of two shapes:
      {"chunk": "text"}              — a piece of the answer as Gemini generates it
      {"done": true, "conversation_history": [...]}  — sent once at the end

    The caller wraps each in "data: ...\\n\\n" for SSE. Errors are yielded as
    {"error": "message", "status": <code>} so the frontend can display them
    even though HTTP headers are already sent by the time we fail.
    """
    # Check for task status update intent before hitting Gemini
    task_update = None
    action = _detect_task_action(question)
    if action:
        task_id, new_status = action
        result = patch_task_status(task_id, new_status)
        task_update = {
            "task_id": task_id,
            "new_status": new_status,
            "title": result.get("title") if result else None,
            "success": result is not None,
        }

    want_graph = _needs_graph(question)
    want_events = _needs_events(question)
    if not want_graph and not want_events:
        want_graph = want_events = True

    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks_future = pool.submit(search_top_tasks, question, api_key, project_id)
        graph_future = pool.submit(fetch_graph) if want_graph else None
        events_future = pool.submit(_safe_fetch_live_events) if want_events else None
        names_future = pool.submit(fetch_project_names)

        relevant_tasks = tasks_future.result()
        graph = graph_future.result() if graph_future else None
        live_events = events_future.result() if events_future else None
        project_names = names_future.result()

    client = genai.Client(api_key=api_key)
    prompt_parts = _build_prompt_parts(
        question, relevant_tasks, conversation_history, live_events, graph,
        project_id, project_names,
    )

    if task_update:
        if task_update["success"]:
            prompt_parts.insert(
                0,
                f"System action: Task {task_update['task_id']} "
                f"(\"{task_update['title']}\") has been updated to "
                f"\"{task_update['new_status']}\". "
                "Confirm this to the user naturally in one sentence.",
            )
        else:
            prompt_parts.insert(
                0,
                f"System action failed: Could not find or update task "
                f"{task_update['task_id']}. Let the user know naturally.",
            )

    full_answer = ""
    for chunk in client.models.generate_content_stream(
        model=MODEL_NAME,
        contents="\n\n".join(prompt_parts),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
        ),
    ):
        if chunk.text:
            full_answer += chunk.text
            yield json.dumps({"chunk": chunk.text})

    updated_history = (conversation_history or []) + [
        {"question": question, "answer": full_answer}
    ]
    done_payload: dict = {"done": True, "conversation_history": updated_history[-5:]}
    if task_update:
        done_payload["task_update"] = task_update
    yield json.dumps(done_payload)


# Fetches live events but never raises — matches how ask_clover treated failures.
def _safe_fetch_live_events():
    """fetch_live_events(), returning None instead of raising on any failure."""
    try:
        return fetch_live_events()
    except Exception:
        return None


_TASK_ID_RE = re.compile(r'\bT\d+\b', re.IGNORECASE)
_COMPLETED_RE = re.compile(r'\b(?:done|finish(?:ed)?|complet(?:ed)?|wrap(?:ped)?\s*up)\b', re.IGNORECASE)
_IN_PROGRESS_RE = re.compile(r'\b(?:start(?:ing|ed)?|working\s+on|began|beginning|picking\s+up)\b', re.IGNORECASE)
_BLOCKED_RE = re.compile(r'\b(?:block(?:ed)?|stuck|can\'t\s+(?:start|do|work))\b', re.IGNORECASE)


def _detect_task_action(question: str) -> tuple[str, str] | None:
    """Return (task_id, new_status) if the question is a status update, else None."""
    task_ids = _TASK_ID_RE.findall(question)
    if not task_ids:
        return None
    task_id = task_ids[0].upper()

    # Explicit "mark T4 as X" takes priority
    mark_match = re.search(r'\bmark\s+T\d+\s+as\s+([\w\s]+)', question, re.IGNORECASE)
    if mark_match:
        label = mark_match.group(1).strip().lower()
        if any(w in label for w in ("complet", "done", "finish")):
            return task_id, "completed"
        if any(w in label for w in ("progress", "start", "active")):
            return task_id, "in_progress"
        if any(w in label for w in ("block", "stuck")):
            return task_id, "blocked"
        if any(w in label for w in ("upcoming", "todo")):
            return task_id, "upcoming"

    if _COMPLETED_RE.search(question):
        return task_id, "completed"
    if _IN_PROGRESS_RE.search(question):
        return task_id, "in_progress"
    if _BLOCKED_RE.search(question):
        return task_id, "blocked"
    return None


_GRAPH_KEYWORDS = {"block", "depend", "skill", "assign", "who is", "who can", "owner", "relationship", "working on", "work on", "assigned to", "responsible"}
_EVENT_KEYWORDS = {"recent", "today", "yesterday", "commit", "push", "discord", "did", "doing", "worked", "activity", "update", "lately", "last week", "this week"}


def _needs_graph(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _GRAPH_KEYWORDS)


def _needs_events(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _EVENT_KEYWORDS)


# Answers a question, running the three independent retrievals concurrently.
def answer_question(
    question: str,
    api_key: str,
    conversation_history: list[dict] = None,
    project_id: str | None = None,
) -> str:
    """End-to-end Clover answer with the retrieval steps parallelised.

    The semantic search, the graph build, and the live-events fetch don't depend
    on each other — only the final Gemini synthesis needs all three. Running them
    in a thread pool (they're all I/O-bound) collapses their latency to the slowest
    single step instead of their sum, then ask_clover does the one LLM call.

    Graph and events are only fetched when the question actually needs them —
    skipping an unnecessary HTTP call or Neo4j query saves real time.
    """
    want_graph = _needs_graph(question)
    want_events = _needs_events(question)
    # If neither keyword set matched, fetch both — better to have too much context
    # than too little for an ambiguous question.
    if not want_graph and not want_events:
        want_graph = want_events = True

    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks_future = pool.submit(search_top_tasks, question, api_key, project_id)
        graph_future = pool.submit(fetch_graph) if want_graph else None
        events_future = pool.submit(_safe_fetch_live_events) if want_events else None
        names_future = pool.submit(fetch_project_names)

        relevant_tasks = tasks_future.result()
        graph = graph_future.result() if graph_future else None
        live_events = events_future.result() if events_future else None
        project_names = names_future.result()

    return ask_clover(
        question,
        relevant_tasks,
        api_key,
        conversation_history,
        project_id=project_id,
        graph=graph,
        live_events=live_events,
        project_names=project_names,
    )


# Runs Clover from the command line: asks a question and prints the answer.
def main() -> None:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to a .env file in the project root."
        )

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:]).strip()
    else:
        question = input("Ask Clover a project question: ").strip()

    if not question:
        raise RuntimeError("Question cannot be empty.")

    conversation_history: list[dict] = []
    answer = answer_question(question, api_key, conversation_history)

    print(f"\nQuestion: {question}\n")
    print("Clover:")
    print(answer)

    conversation_history.append({"question": question, "answer": answer})
    conversation_history = conversation_history[-5:]


if __name__ == "__main__":
    main()
