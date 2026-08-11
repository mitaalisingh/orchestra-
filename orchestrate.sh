#!/usr/bin/env bash
# Orchestra — interactive live demo.
# Type a project idea, hit Enter → it calls Gemini via the AI service, breaks the
# idea into an assigned task graph, stores it in Neo4j + the backend Postgres, and
# then lets you ask Clover (Graph-RAG) questions about it.
#
# Usage:  ./orchestrate.sh
#
# Reads INTERNAL_API_KEY + creds from .env.

set -u
cd "$(dirname "$0")"
set -a; source .env; set +a

AI="https://orchestra-ai-36zm.onrender.com"
BE="https://orchestra-backend-30fy.onrender.com"
KEY="${INTERNAL_API_KEY:?INTERNAL_API_KEY missing from .env}"

bold(){ echo -e "\033[1;36m$*\033[0m"; }
dim(){ echo -e "\033[2m$*\033[0m"; }
green(){ echo -e "\033[1;32m$*\033[0m"; }

clear
bold "╭───────────────────────────────────────────────╮"
bold "│   ORCHESTRA — AI project orchestrator (live)  │"
bold "╰───────────────────────────────────────────────╯"
echo

# ── Pre-warm so the first real call isn't a 40s cold start ──────────────────
printf "  Waking the AI service"
for i in 1 2 3 4 5 6 7 8; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 90 "$AI/tasks" || true)
  [ "$code" = "200" ] && { echo " ready."; break; }
  printf "."; sleep 3
done
echo

# ── 1. Collect the idea ─────────────────────────────────────────────────────
read -rp "$(bold 'Project name: ')" NAME
[ -z "${NAME:-}" ] && NAME="Untitled Project"
echo
bold "Describe the idea (what should this app do?) then press Enter:"
read -r IDEA
[ -z "${IDEA:-}" ] && { echo "  (no idea entered — exiting)"; exit 1; }
echo
read -rp "$(bold 'Tech stack (comma-separated, or Enter for a default): ')" STACK
[ -z "${STACK:-}" ] && STACK="Python,FastAPI,Neo4j,React"

# Build JSON arrays from the comma lists (members = the real team).
STACK_JSON=$(python3 -c "import json,sys; print(json.dumps([s.strip() for s in sys.argv[1].split(',') if s.strip()]))" "$STACK")
MEMBERS_JSON='["Naman","Mitaali","Arnav","Sarvyagya","Prince","Isha"]'
BODY=$(python3 -c "import json,sys; print(json.dumps({'name':sys.argv[1],'description':sys.argv[2],'tech_stack':json.loads(sys.argv[3]),'members':json.loads(sys.argv[4])}))" \
  "$NAME" "$IDEA" "$STACK_JSON" "$MEMBERS_JSON")

echo
dim "  → Sending to Gemini: planning tasks, scoping assignment to the team,"
dim "    ingesting to Neo4j, pushing to the backend Postgres…"
echo

# ── 2. Orchestrate: POST /blueprint (Gemini) ────────────────────────────────
RESP=$(curl -s -X POST "$AI/blueprint" -H "Content-Type: application/json" \
  -H "x-api-key: $KEY" --max-time 180 -d "$BODY")

echo "$RESP" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("  (could not parse response)"); sys.exit()
if "tasks" not in d:
    print("  Server said:", d.get("detail", d)); sys.exit()
ts=d.get("tasks",[])
print("  \033[1;32m✓ Orchestrated %d tasks for %r\033[0m\n" % (len(ts), d.get("project_name")))
if d.get("summary"): print("  Summary:", d["summary"][:180], "\n")
print("  %-4s %-46s %-12s %s" % ("ID","TASK","ASSIGNEE","DEPENDS ON"))
print("  " + "-"*84)
for t in ts:
    dep=",".join(t.get("dependencies") or t.get("depends_on") or []) or "-"
    print("  %-4s %-46s %-12s %s" % (t["id"], t["title"][:46], t.get("assigned_to","?"), dep))
'

echo
green "  Stored live in Neo4j + backend Postgres under the same task ids."
echo

# ── 3. Ask Clover about it (loop) ───────────────────────────────────────────
bold "Now ask Clover about the project (Graph-RAG). Blank line to quit."
while true; do
  echo
  read -rp "$(bold 'You: ')" Q
  [ -z "${Q:-}" ] && { echo; dim "  Done. The graph + Clover are live at $AI"; break; }
  QJSON=$(python3 -c "import json,sys; print(json.dumps({'question':sys.argv[1]}))" "$Q")
  dim "  (thinking…)"
  curl -s -X POST "$AI/clover" -H "Content-Type: application/json" \
    -H "x-api-key: $KEY" --max-time 180 -d "$QJSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
ans=d.get("answer") or d.get("response") or d.get("detail") or json.dumps(d)[:300]
print("\033[1;35mClover:\033[0m")
for line in str(ans).splitlines(): print("  "+line)
'
done
