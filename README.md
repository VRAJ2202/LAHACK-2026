# 🧠 SpecMem — Memory-Powered Debugging Agent

> **AI that learns from past debugging experience so it never repeats the same mistakes.**

SpecMem is a CLI tool that wraps your terminal commands, automatically captures errors, tracks fix attempts via `git diff`, and uses past debugging history to give smarter AI suggestions — or fix bugs entirely on its own.

---

## The Problem

Every AI coding tool today — Copilot, Cursor, Claude Code — is **stateless**. They forget everything after each session. This means:

- They repeat the same failed fixes
- They can't learn from what worked before
- Developers waste time re-explaining context
- Tokens are wasted on redundant information

**SpecMem gives AI memory and experience.**

---

## Three Modes

### `specmem run "python app.py"` — Detect

Runs your command through SpecMem. If it crashes, automatically captures the error (traceback, file paths, error type), stores it in memory, and gives you an AI-powered suggestion.

### `specmem fix "python app.py"` — Learn

After you edit your code, re-runs the command and checks if your fix worked. Captures your `git diff` and records it as a **failed fix** or **successful fix**. SpecMem learns what works and what doesn't.

### `specmem agent "python app.py"` — Solve

Fully autonomous. Runs the command, detects the error, queries memory, asks Gemini to generate a fix, applies it to the file automatically, re-runs, and repeats — until the bug is fixed. **Zero human input.**

---

## How It Works

```
specmem run "python app.py"
        ↓
Executes command via subprocess
        ↓
Captures stdout / stderr / exit code
        ↓
If error detected:
    → Parses traceback automatically
    → Stores in MongoDB with embedding
    → Searches similar past bugs (vector search)
    → Injects memory into Gemini prompt
    → Returns smarter fix suggestion
```

### Without SpecMem
```
"Fix login bug" → generic answer, starts from scratch
```

### With SpecMem
```
"You already tried increasing timeout — it failed.
 Root cause was async race condition → try refreshing token before retrying."
```

---

## Demo

### 1. Auto-capture an error
```bash
$ specmem run "python app.py"

❌ ZeroDivisionError: division by zero
📝 Episode captured!

🧠 SpecMem Suggestion:
   Add a check for an empty list before division.
```

### 2. Try a bad fix → SpecMem records it
```bash
$ specmem fix "python app.py"

❌ Fix Failed — recorded in memory.
   SpecMem will warn about this approach in the future.
```

### 3. Apply the real fix → SpecMem learns
```bash
$ specmem fix "python app.py"

✅ Fix Successful — stored in memory.
   Future errors like this will get better suggestions.
```

### 4. Different file, same bug → SpecMem already knows
```bash
$ specmem run "python app2.py"

🧠 This parallels past issues. Add an empty list check
   before division. Do not clear the cache — that failed before.
```

### 5. Fully autonomous fix
```bash
$ specmem agent "python app3.py"

🤖 Step 1: KeyError detected → querying memory → generating fix → applying...
✅ Step 2: Command succeeded! Zero human input.
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Auto error capture** | Detects errors from exit code + stderr parsing |
| **Auto fix tracking** | Captures `git diff`, records as failed or successful |
| **Cross-file learning** | Fixing `app.py` teaches AI about similar bugs in `app2.py` |
| **Failed fix prevention** | Warns before repeating a previously failed approach |
| **Semantic search** | Finds similar bugs using Gemini embeddings + MongoDB vector search |
| **Autonomous agent** | Detects, generates fix, applies, re-runs — fully automatic |
| **Token savings** | Sends only relevant memory context (98%+ reduction) |
| **Visual dashboard** | Streamlit shows episode lifecycle: 🔴 open → 🟡 fixing → 🟢 resolved |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Backend | FastAPI |
| Database | MongoDB Atlas |
| Vector Search | MongoDB Atlas Vector Search |
| LLM | Google Gemini (gemini-2.5-flash) |
| Embeddings | Gemini (gemini-embedding-001, 3072 dims) |
| Dashboard | Streamlit |
| CLI | Typer + Rich |

---

## Architecture

```
VS Code Terminal
    ↓
specmem run / fix / agent
    ↓
FastAPI Backend (13 endpoints)
    ↓
┌────────────────────────────┐
│  Gemini          MongoDB   │
│  Embeddings      Atlas     │
│  (3072-dim)      Vector    │
│                  Search    │
└────────┬───────────────────┘
         ↓
  Gemini LLM (gemini-2.5-flash)
         ↓
  Memory-Enhanced Debug Response
         ↓
  CLI Output + Streamlit Dashboard
```

---

## Project Structure

```
specmem/
├── backend/
│   ├── config.py              # Environment variables
│   ├── schemas.py             # Pydantic models
│   ├── database.py            # MongoDB connection + indexes
│   ├── memory_service.py      # CRUD for memories + episodes
│   ├── error_parser.py        # Auto-parse stderr → structured error
│   ├── retrieval_service.py   # Gemini embeddings + vector search
│   ├── llm_service.py         # Gemini LLM agent + token savings
│   ├── agent_loop.py          # Autonomous fix loop
│   └── main.py                # FastAPI (13 endpoints)
├── frontend/
│   └── streamlit_app.py       # Debug Episodes dashboard
├── cli/
│   └── cli.py                 # 8 CLI commands
├── requirements.txt
└── .env.example
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/VRAJ2202/LAHACK-2026.git
cd LAHACK-2026
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in your `.env`:

```env
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=specmem
GEMINI_API_KEY=your-gemini-api-key
BACKEND_URL=http://localhost:8000
```

Get your keys:
- **MongoDB Atlas** — [cloud.mongodb.com](https://cloud.mongodb.com) (free M0 tier)
- **Gemini API** — [aistudio.google.com](https://aistudio.google.com)

### 3. Create MongoDB Vector Indexes

In MongoDB Atlas → Search & Vector Search → Create Search Index:

**For `bug_memories` collection** (index name: `vector_index`):
```json
{
  "fields": [{
    "type": "vector",
    "path": "embedding",
    "numDimensions": 3072,
    "similarity": "cosine"
  }]
}
```

**For `debug_episodes` collection** (index name: `episode_vector_index`):
```json
{
  "fields": [{
    "type": "vector",
    "path": "embedding",
    "numDimensions": 3072,
    "similarity": "cosine"
  }]
}
```

### 4. Run

```bash
# Terminal 1 — Backend
uvicorn specmem.backend.main:app --reload

# Terminal 2 — Dashboard
streamlit run specmem/frontend/streamlit_app.py

# Terminal 3 — Use SpecMem
export GEMINI_API_KEY="your-key"
python -m specmem.cli.cli run "python app.py" --project-id my-project
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `specmem agent "<cmd>"` | 🤖 Autonomous — detect, fix, retry automatically |
| `specmem run "<cmd>"` | Run command, auto-capture errors |
| `specmem fix "<cmd>"` | Re-run after editing, track fix via git diff |
| `specmem debug "<query>"` | Query memory for debugging help |
| `specmem check "<fix>"` | Check if a proposed fix has failed before |
| `specmem remember` | Manually save a bug memory |
| `specmem memories` | List stored memories |
| `specmem episodes` | List auto-captured episodes |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/memory` | Store bug memory |
| GET | `/memory/{id}` | Get memory by ID |
| GET | `/memory` | List memories by project |
| POST | `/debug` | Memory-powered debug query |
| POST | `/check` | Check if fix failed before |
| POST | `/extract` | Auto-extract memory from raw text |
| PATCH | `/memory/{id}/feedback` | Mark fix as worked/failed |
| GET | `/episodes` | List auto-captured episodes |
| GET | `/episodes/{id}` | Get episode by ID |
| POST | `/episodes/capture` | Capture error from CLI |
| POST | `/episodes/fix-result` | Record fix result from CLI |
| POST | `/token-log` | Log token usage |

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Token savings | 98.93% (31,880 → 341 tokens) |
| Embedding dimensions | 3,072 |
| Vector similarity | Cosine |
| Error detection | Automatic (exit code + stderr) |
| Fix tracking | Automatic (git diff) |
| Agent auto-fix | 1-2 steps average |

---

## The "It Actually Learns" Moment

1. `specmem run "python app.py"` → ZeroDivisionError captured
2. Developer tries bad fix → `specmem fix` records it as failed
3. Developer applies real fix → `specmem fix` records it as successful 🟢
4. `specmem run "python app2.py"` → **Different file, same bug pattern** → SpecMem immediately suggests the correct fix from app.py's memory
5. `specmem agent "python app3.py"` → **Fully autonomous** — fixes a KeyError bug with zero human input

---

## Built at LA HACK 2026

SpecMem was built in 24 hours at LA HACK 2026.

---

## License

MIT
