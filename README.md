# civil-agent

An autonomous AI assistant for **civil engineers, construction managers, urban planners, and their clients** — running entirely locally on a free Meta Llama model via [Ollama](https://ollama.com). No API keys. No cloud costs.


---

## What it does

### 1. Persistent Engineering Agent (`main.py`)

A conversational agent that remembers everything across sessions and tracks your active projects.

- Answers technical questions referencing ACI 318, AISC, AASHTO, OSHA, IBC, and local codes
- Tracks **projects, RFIs, submittals, and site issues** — all persisted to local SQLite
- Switches register automatically: technical language for engineers, plain English for clients
- Builds a self-model over time — priorities, patterns, and project history accumulate across conversations
- Flags safety concerns immediately and without softening
- Never guesses on structural calculations — states clearly when licensed review is required

### 2. Support Triage Pipeline (`run_triage.py`)

A production-grade ticket classifier and response drafter for incoming queries from engineers, contractors, and clients.

- **Classifies** tickets across 10 construction categories with priority, sentiment, and routing
- **Searches** a knowledge base for known resolutions before generating a response
- **Drafts** context-aware replies — escalating tone for urgent issues, plain English for clients
- **Auto-resolves** high-confidence standard queries; escalates safety issues with stop-work language
- Full audit trail for every triage decision

---

## Who it's for

| Role | Use case |
|---|---|
| **Civil / Structural Engineer** | RFI management, code reference, design review questions |
| **Construction Manager** | Project phase tracking, change order advice, schedule issues |
| **Urban Planner** | Zoning variance guidance, environmental review, permit process |
| **Client / Owner** | Plain-English project status updates, timeline and cost impact summaries |

---

## Architecture

```
civil-agent/
│
├── main.py                   ← Autonomous agent CLI (Rich terminal UI)
├── run_triage.py             ← Support triage pipeline CLI
├── config.py                 ← Ollama host, model, all paths
│
├── core/
│   ├── agent.py              ← Orchestrator: memory + tools + Ollama loop
│   ├── kernel.py             ← LCRK: event-driven state updates per message
│   ├── identity.py           ← Loads identity files → builds system prompt
│   ├── inner_state.py        ← Persistent working thread (focus, loops, tasks)
│   ├── priority_memory.py    ← PMS: 50 active insights across 5 categories
│   ├── reflection.py         ← LLM-driven daily/weekly distillation cycles
│   └── memory/
│       ├── episodic.py       ← Conversation history + session records
│       ├── semantic.py       ← Long-term memory with FTS5 full-text search
│       ├── self_model.py     ← Self-image, diary, self-authored rules
│       ├── personality.py    ← Mood, energy, curiosity, focus state
│       ├── user_profile.py   ← Learned facts about each user
│       ├── thoughts.py       ← Inter-session internal monologue
│       └── consolidation.py  ← LMCS: anchors, weekly essences, patterns
│
├── pipeline/
│   ├── classifier.py         ← Zero-shot ticket classifier + rule-based fallback
│   ├── drafter.py            ← Response drafter with KB lookup + tone routing
│   ├── workflow.py           ← Full triage pipeline orchestrator
│   ├── ticket_store.py       ← SQLite: tickets, classifications, responses, KB
│   └── projects.py           ← Project/RFI/submittal/site-issue tracker
│
├── tools/
│   ├── file_tools.py         ← Sandboxed read/write tools (notes, journal, KB)
│   └── construction_tools.py ← 9 project management tools for the agent
│
└── identity/
    ├── AGENT.txt             ← Core expertise and values (edit to customize)
    ├── knowledge.txt         ← Pre-seeded construction domain knowledge
    ├── daily_reflection.txt  ← Auto-updated each day by the agent
    ├── red_thread.txt        ← Narrative thread, updated every 15 turns
    ├── journal.txt           ← Agent's own diary entries
    ├── self_rules.json       ← Rules the agent writes for itself over time
    └── notes/                ← Agent's writable scratchpad
```

### Data flow per conversation turn

```
User message
  → kernel.py          event-driven state update (focus, open loops, tasks)
  → semantic.py        search relevant memories to inject into context
  → identity.py        build system prompt: identity + rules + memories + state
  → agent.py           call Ollama → execute tools in loop → final response
  → episodic.py        store the turn
  → inner_state.json   persisted to disk
  → (every 15 turns)   red thread narrative updated
  → (daily)            reflection + anchor distillation
```

### Memory pyramid (LMCS)

```
Active turns (episodic) → Session summary → Daily reflection
  → Weekly essence → Pattern consolidation → Core anchors
```

---

## Quick start

### 1. Install Ollama

Download from [ollama.com/download](https://ollama.com/download) and install. Ollama runs as a background service.

### 2. Pull a Meta Llama model

```bash
# Fast (3B, ~2GB) — good for most queries
ollama pull llama3.2

# Better quality (8B, ~5GB) — recommended for technical work
ollama pull llama3.1:8b
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

Requires Python 3.11+. No other system dependencies.

### 4. Run

```bash
# Autonomous agent
python main.py

# Support triage pipeline
python run_triage.py seed          # load demo construction tickets
python run_triage.py process-all   # classify + draft all pending tickets
python run_triage.py queue         # view the ticket queue
```

---

## Agent usage

Start the agent and talk to it like a senior technical advisor:

```
You: Create a project called Riverside Bridge Replacement, client City of Greenwood, target 2026-03-15

You: Log a critical site issue on Riverside Bridge — groundwater encountered at 6ft during pier excavation,
     expected at 12ft per geotech report

You: Create an RFI for Riverside Bridge: footing reinforcement spacing conflict between structural S-3
     and architectural A-7 at grid line B

You: What are the minimum concrete cover requirements for footings cast against earth per ACI 318?

You: Write a plain-English status update for the Riverside Bridge client explaining the groundwater issue
     and its impact on the schedule
```

### Agent slash commands

| Command | Description |
|---|---|
| `/state` | Current focus, open loops, unfinished tasks |
| `/memories` | Top 50 priority memories across 5 categories |
| `/rules` | Self-authored rules the agent has written |
| `/reflect` | Trigger manual daily reflection |
| `/sessions` | Recent session summaries |
| `/profile` | Learned facts about you |
| `/quit` | End session and save |

### What the agent tracks across sessions

- Active projects and their current phase
- Open RFIs, pending submittals, site issues by severity
- Your preferences and communication style
- Technical decisions made in previous conversations
- Patterns in the questions you ask most frequently

---

## Triage pipeline usage

```bash
python run_triage.py seed           # load 5 demo tickets + 10 KB entries
python run_triage.py process-all    # run full triage on all pending tickets
python run_triage.py process 3      # triage a specific ticket
python run_triage.py view 3         # inspect ticket, classification, draft, log
python run_triage.py queue          # full ticket queue with status/priority
python run_triage.py metrics        # pipeline stats
python run_triage.py submit         # interactive ticket submission
```

### Classification dimensions

| Dimension | Values |
|---|---|
| **Category** | `rfi` `site_issue` `design_review` `permit_approval` `budget_cost` `schedule` `safety` `client_inquiry` `zoning_planning` `submittal` `general` |
| **Priority** | `critical` `high` `medium` `low` |
| **Sentiment** | `urgent` `concerned` `neutral` `positive` |
| **Routing** | `engineer` `project_manager` `client_notify` `auto_resolve` `escalate` |

Safety issues are always routed to `escalate` with a stop-work recommendation in the draft response.

---

## Configuration

Create a `.env` file in the project root to override defaults:

```env
OLLAMA_HOST=http://localhost:11434
AGENT_MODEL=llama3.1:8b
```

No API keys required.

---

## Tech stack

| Component | Technology |
|---|---|
| LLM engine | Meta Llama 3.2 / 3.1 via [Ollama](https://ollama.com) |
| LLM client | `ollama` Python library |
| Memory storage | SQLite (7 databases) + FTS5 full-text search |
| Terminal UI | [Rich](https://github.com/Textualize/rich) |
| Environment | Python 3.11+ |

Everything runs locally. No data leaves your machine.

---

## License

MIT
