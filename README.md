<p align="center">
  <img src="./capy.png" width="150" height="150" alt="Capy Memory logo" />
</p>

<h1 align="center">Capy Memory</h1>

<p align="center">
  <strong>A warm companion that turns useful conversation details into durable, searchable memory.</strong>
</p>

<p align="center">
  Capy combines an chat model, local embeddings, SQLite, and FAISS so a conversation can feel personal without treating every message as permanent truth.
</p>

---

## Why Capy

Most chat sessions start from zero. Capy keeps the details that make follow-up conversations useful: preferences, professional background, ongoing plans, and time-sensitive situations worth revisiting.

It is designed to:

- extract durable user facts from each turn;
- distinguish semantic facts from time-bound episodic moments;
- update, replace, or deactivate memories as preferences change;
- retrieve relevant memory with local embeddings and FAISS;
- keep messages, summaries, and memory records in a local SQLite database; and
- stay honest when a detail was never supplied.

Capy is a companion-memory reference application. It is not an authenticated, multi-user production service.

## Experience

```text
User message
    │
    ▼
Retrieve relevant active memories
    │
    ▼
Capy response with memory context
    │
    ▼
Extract facts and significant moments
    │
    ▼
Update SQLite records and the FAISS index
    │
    ▼
Use the refreshed memories on later turns
```

## Architecture at a glance

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Interactive app | Python CLI | Creates or resumes a conversation, accepts input, and prints Capy's response. |
| Chat model | General Compute by default | Generates Capy's responses, extracts memories, classifies semantic updates, and produces summaries. |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` by default | Produces local 384-dimensional vectors for retrieval. |
| Memory search | FAISS `IndexFlatIP` | Performs exact inner-product search over normalized memory embeddings. |
| Durable storage | SQLite with SQLAlchemy | Stores profiles, conversations, messages, summaries, and active/inactive memories. |
| Tests | Pytest | Covers configuration, persistence, embeddings, memory lifecycle, summaries, and optional live end-to-end flows. |

For the complete component design, data flow, search behavior, and operational notes, see [DESIGN.md](./DESIGN.md).

## Repository layout

```text
.
├── capy.png                    # Capy logo used by this README
├── main.py                     # Interactive CLI entry point
├── src/capy/
│   ├── core/                   # Settings and OpenAI-compatible clients
│   ├── db/                     # SQLAlchemy engine and database models
│   ├── memory/                 # Extraction, updates, bubbles, FAISS, retrieval
│   ├── prompts/                # Extraction, update, and summary instructions
│   └── utils/                  # Conversation summary generation
├── tests/                      # Offline and live pytest coverage
├── DESIGN.md                   # High-level architecture and design decisions
├── pyproject.toml              # Package metadata and test configuration
└── uv.lock                     # Locked dependency graph
```

## Getting started

### Prerequisites

- [Python](https://www.python.org/) 3.13 or later
- [uv](https://docs.astral.sh/uv/)
- A General Compute API key for chat, extraction, semantic updates, and summaries

The default embedding model runs locally. Its first use may download model weights from Hugging Face; `HF_TOKEN` is optional but can improve Hugging Face rate limits.

### Install dependencies

```powershell
uv sync
```

### Configure Capy

Create a local `.env` file in the repository root:

```env
# Required for the default chat provider
GENERAL_COMPUTE_API_KEY=your_general_compute_api_key

# Default chat configuration
LLM_PROVIDER=general_compute
GENERAL_COMPUTE_BASE_URL=https://api.generalcompute.com/v1
LLM_MODEL=gpt-oss-120b

# Local embeddings avoid embedding API credits
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Local persistence
DATABASE_URL=sqlite:///./data/capy_memory.db
DEBUG=false
```

### Run the interactive companion

```powershell
uv run python main.py
```

At startup, choose a conversation ID to resume or press Enter to create one. In the chat loop:

| Input | Result |
| --- | --- |
| Any message | Sends a message to Capy and persists the resulting user/assistant pair. |
| `memories` | Displays active memory matches for the current conversation. |
| `exit` or `quit` | Ends the session. |

The sample CLI uses the demo profile name `Shashank`. It is intentionally small and can be adapted to accept profile identity from a UI or application layer.

## How memory is managed

Capy stores two kinds of memory:

- **Semantic facts** are long-lived details such as a role, preference, location, or regular technology choice.
- **Episodic bubbles** are significant, time-bound moments such as an active blocker, a deadline, or an explicit plan.

For semantic facts, Capy asks a memory-management model to choose one of five actions:

| Action | Meaning |
| --- | --- |
| `ADD` | Store a new fact. |
| `UPDATE` | Enrich an existing fact. |
| `REPLACE` | Soft-deactivate a contradictory fact and save the new one. |
| `DELETE` | Soft-deactivate a memory. |
| `NOOP` | Keep the existing record unchanged. |

Memory retrieval is scoped to the selected conversation. Capy embeds the latest user message, searches the active FAISS index, and supplies up to ten relevant results to the chat model.

## Testing

Run the safe, non-credit-consuming suite:

```powershell
uv run pytest tests -v -m "not live"
```

Run all tests, including General Compute live tests, only when the environment is configured and API usage is intended:

```powershell
$env:CAPY_RUN_LIVE_E2E = "1"
uv run pytest tests -v
Remove-Item Env:CAPY_RUN_LIVE_E2E
```

Live tests require `GENERAL_COMPUTE_API_KEY` and consume provider credits. They verify the configured chat provider, `gpt-oss-120b`, local embeddings, the interactive flow, and database persistence against real services.

## Privacy and local data

Capy writes the following generated artifacts beneath `data/` by default:

```text
data/
├── capy_memory.db                 # SQLite profiles, messages, summaries, memories
└── capy_memory/indexes/
    ├── conv_<id>.faiss            # Per-conversation FAISS index
    └── conv_<id>.map.json         # Memory-ID mapping for that index
```

These files are intentionally ignored by Git. Treat them as local user data. The configured chat provider receives the current message and relevant memory context; extraction, update classification, and summaries also use the configured LLM. Do not put API keys, passwords, or other secrets into a conversation.

## Current scope

Capy is built as a clear, inspectable memory pipeline for a CLI companion. Current limitations are deliberate areas for future work:

- memory retrieval is conversation-scoped even though records are associated with a profile;
- the response prompt uses the current message and retrieved memories, rather than full recent chat history;
- the `memories` command is a broad semantic lookup, not a raw database administration view;
- there is no authentication, authorization, encryption-at-rest, or schema migration layer; and
- long-running deployments should add stronger deduplication, retention, and operational controls.

## Contributing

Keep changes focused, avoid committing `.env` or `data/`, and update tests when changing extraction, indexing, ranking, persistence, or provider behavior. Before opening a change, run the non-live test suite.

---

Built with care for conversations that deserve a little continuity.
