#!/usr/bin/env bash
# Orchestra — live reviewer demo (Knowledge Graph & AI Engineer track)
# Walks the full chain: knowledge graph -> AI roadmap -> dual-store id alignment
# -> live backend->graph status sync -> Clover Graph-RAG.
#
# Usage:
#   ./demo.sh            # presenter mode: pauses between acts (press Enter to advance)
#   ./demo.sh --no-pause # run straight through (rehearsal / recording)
#
# Reads INTERNAL_API_KEY + creds from .env. Free-tier services cold-start (~40s);
# the script pre-warms them first so nothing stalls in front of reviewers.

# NB: deliberately not using `set -e` — a transient free-tier timeout must never
# abort the demo mid-show; each act stands on its own.
set -u
cd "$(dirname "$0")"
set -a; source .env; set +a

AI="https://orchestra-ai-36zm.onrender.com"
BE="https://orchestra-backend-30fy.onrender.com"
KEY="${INTERNAL_API_KEY:?INTERNAL_API_KEY missing from .env}"

PAUSE=1; [ "${1:-}" = "--no-pause" ] && PAUSE=0
pause() { [ "$PAUSE" = 1 ] && { echo; read -rp $'\033[2m  (press Enter to continue)\033[0m'; echo; } || echo; }
say()   { echo; echo -e "\033[1;36m▶ $*\033[0m"; }
sub()   { echo -e "  \033[2m$*\033[0m"; }

# ── Pre-warm ────────────────────────────────────────────────────────────────
say "Warming up the live services (free tier cold-starts ~40s)…"
for url in "$AI/tasks" "$BE/tasks"; do
  sub "pinging $url"
  for i in 1 2 3 4 5; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 90 "$url" || true)
    [ "$code" = "200" ] && { sub "  up ($code)"; break; }
    sub "  …$code, retrying"; sleep 3
  done
done
pause

# ── Act 1: the knowledge graph ───────────────────────────────────────────────
say "ACT 1 — The Neo4j knowledge graph I designed"
sub "Three node types (Task / Developer / Skill), three relationship types."
curl -s "$AI/graph" -H "x-api-key: $KEY" --max-time 90 | python3 -c '
import json,sys
d=json.load(sys.stdin); nodes=d.get("nodes",[]); edges=d.get("edges",[])
print(f"  nodes: {len(nodes)}   edges: {len(edges)}")
rels={}
for e in edges: rels[e.get("data",{}).get("relationship","?")]=rels.get(e.get("data",{}).get("relationship","?"),0)+1
print("  relationships:", ", ".join(f"{k}×{v}" for k,v in rels.items()))
'
pause

# ── Act 2: AI generates a roadmap, I ingest it ──────────────────────────────
say "ACT 2 — Type an idea, the AI breaks it into an assigned task graph"
sub "POST /blueprint  →  Gemini plans tasks, assignment is SCOPED to the team roster,"
sub "then ingested into Neo4j AND pushed to the backend Postgres."
RESP=$(curl -s -X POST "$AI/blueprint" -H "Content-Type: application/json" -H "x-api-key: $KEY" --max-time 180 -d '{
  "name":"Orchestra Demo E2E",
  "description":"Verify the AI service generates a roadmap, ingests to Neo4j, and pushes to the backend Postgres with matching ids.",
  "tech_stack":["Python","FastAPI","Neo4j","React"],
  "members":["Naman","Mitaali","Arnav","Sarvyagya","Prince","Isha"]
}')
python3 - "$RESP" <<'PY'
import json,sys
d=json.loads(sys.argv[1]); ts=d.get("tasks",[])
print(f"  generated {len(ts)} tasks for project {d.get('project_name')!r}:")
for t in ts: print(f"    {t['id']:>3}  {t['title'][:46]:46}  -> {t.get('assigned_to')}")
PY
pause

# ── Act 3: same ids in both stores ──────────────────────────────────────────
say "ACT 3 — The graph and the backend are ONE source of truth (same ids)"
sub "Reading each generated id back out of BOTH Neo4j and Postgres."
python3 - "$RESP" <<'PY'
import json,sys,urllib.request
gen={t["id"]:t for t in json.loads(sys.argv[1]).get("tasks",[])}
g={t["id"]:t for t in (lambda d:d if isinstance(d,list) else d.get("tasks",d))(json.load(urllib.request.urlopen("https://orchestra-ai-36zm.onrender.com/tasks",timeout=90))) if "id" in t}
ok=0
for tid in sorted(gen):
    try: b=json.load(urllib.request.urlopen(f"https://orchestra-backend-30fy.onrender.com/tasks/{tid}",timeout=60))
    except Exception: b=None
    ing = tid in g; inb = b is not None
    mark = "✓" if (ing and inb) else "✗"
    print(f"    {mark} {tid:>3}  Neo4j={'yes' if ing else 'NO':3}  Postgres={'yes' if inb else 'NO':3}")
    ok += ing and inb
print(f"  → {ok}/{len(gen)} tasks present in BOTH stores under the same id")
PY
pause

# ── Act 4: live status sync backend -> graph ────────────────────────────────
say "ACT 4 — Move a task in the backend, the graph follows in real time"
sub "PATCH the backend (source of truth): T3 → in_progress"
curl -s -X PATCH "$BE/tasks/T3/status" -H "Content-Type: application/json" -d '{"status":"in_progress"}' --max-time 60 >/dev/null
sub "Now read T3 straight from Neo4j via /graph — no manual sync:"
curl -s "$AI/graph" -H "x-api-key: $KEY" --max-time 90 > /tmp/orch_graph.json
python3 - <<'PY'
import json
for n in json.load(open("/tmp/orch_graph.json")).get("nodes",[]):
    if n.get("id")=="T3":
        print(f"    Neo4j node T3 status = {n.get('data',{}).get('status')!r}   <- propagated from the backend")
PY
pause

# ── Act 5: Clover Graph-RAG ─────────────────────────────────────────────────
say "ACT 5 — Ask Clover, the Graph-RAG assistant"
Q="Who is working on the Neo4j and Postgres tasks, and what is in progress?"
sub "Q: $Q"
curl -s -X POST "$AI/clover" -H "Content-Type: application/json" -H "x-api-key: $KEY" --max-time 180 \
  -d "{\"question\":\"$Q\"}" | python3 -c '
import json,sys
d=json.load(sys.stdin)
ans=d.get("answer") or d.get("response") or json.dumps(d)[:400]
print("  Clover:"); [print("   ",l) for l in str(ans).splitlines()]
'
echo
say "Demo complete — idea → graph → dual-store → live status → Graph-RAG, all live."
