# Capy Memory Evaluation

## Purpose

This document records the repeatable evidence for Capy's memory and companion-policy behavior. The repository also contains live end-to-end tests, but the evaluation below is intentionally offline so it can be rerun without an API key or provider cost.

## Latest result

Command:

```powershell
uv run python evals/run_evals.py
```

Result:

```text
mode=offline-deterministic-prompt-contract
scenarios=6
passed=45 failed=0 total=45 pass_rate=1.000
```

## Scenario coverage

| Scenario | Checks |
| --- | --- |
| Explicit preference recall | Retrieves the supplied preference, includes it in the response, excludes an unrelated alternative, and returns only active records. |
| Current fact replacing a plan | Retires a planned location, keeps the newer current location active, and prevents the old plan from being returned as current. |
| Unknown personal detail | Returns an explicit unknown response instead of inventing a sibling's name. |
| Secret refusal | Blocks a synthetic password from active memory and refuses to reveal it without exposing the sentinel value. |
| Episodic recency | Ranks a recent deployment blocker above an older blocker using importance and recency. |
| 51-turn long horizon | Replays 51 turns with early personal facts and later distractors, then verifies that the important facts remain retrievable and an invented fact is excluded. |

## What this proves

The harness gives deterministic evidence for the following contracts:

- active memories can be retrieved after unrelated turns;
- replacement deactivates an older state;
- recency affects episodic ranking;
- unknown details remain unknown;
- synthetic secrets are excluded from memory and response text; and
- a 51-turn fixture retains the declared memory anchors.

The application's offline pytest suite provides complementary implementation coverage for SQLite persistence, local embeddings, FAISS lifecycle, stale-index rebuilding, semantic replacement, recent-bubble consolidation, summary upserts, and bounded chat context.

## What this does not prove

The default harness does not call the application, SQLite, FAISS, Hugging Face, or the configured LLM. It uses explicit fixture events and deterministic mock retrieval/response policies. Therefore its `45/45` result is a **prompt-contract and memory-policy result**, not a live measurement of model reasoning, tone, extraction accuracy, or production latency.

A future live evaluation can replay the same synthetic cases through the real chat loop, but it should remain opt-in and report provider/model, prompt version, failures, latency, and cost separately. No live result is claimed here.

## Walkthrough use

For the assignment walkthrough, pair this report with a short live demonstration:

1. Introduce a personal fact and an ongoing task.
2. Ask a focused recall question.
3. Change a preference and show the replacement behavior.
4. Type `memories` to inspect stored active records.
5. Exit and resume the same conversation ID.
6. Run the offline test and this evaluation command.
7. Explain the remaining boundaries: conversation-scoped retrieval, conservative deduplication, local unencrypted artifacts, and no authentication.
