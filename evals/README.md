# Companion-memory evaluation harness

This directory is a small, offline-first harness for the companion-memory
requirements. It is intentionally isolated from the application and does not
edit or import the production memory pipeline.

## What it evaluates

`scenarios.v1.json` is a versioned fixture file (`schema_version` `1.0`) with
six prompt-contract scenarios:

- recalling an explicitly supplied preference;
- replacing a planned location with a newer current location;
- admitting an unknown personal detail instead of guessing;
- refusing to retain or reveal a synthetic secret-like value;
- ranking a recent episodic event ahead of an older event; and
- recalling a persona after exactly 51 turns containing early facts and later
  distractors.

Each scenario has user turns and explicit `memory_events`. The latter are
**mock extractor outputs**, not facts inferred by the harness from prose. This
makes the checks repeatable and keeps the test focused on memory lifecycle,
retrieval, and response-policy contracts.

## What it does not evaluate

The default run is named `offline-deterministic-prompt-contract` on purpose. It
uses:

- a tiny in-memory store for active/inactive records;
- a deterministic lexical retriever with fixed episodic recency decay; and
- fixed response templates for memory recall, unknown details, and secret
  refusal.

It does **not** call an LLM, the configured provider, embeddings, FAISS,
SQLite, or the application itself. Therefore a passing run is not evidence of:

- real LLM recall or reasoning quality;
- extraction quality from natural language;
- prompt-injection resistance;
- production database/index behavior;
- response tone, usefulness, or factuality outside these fixtures; or
- live-provider availability.

The harness reports no live results and makes no claim about model quality.
The synthetic secret in the fixture is a sentinel, not a real credential.

## Run it

From the repository root, with Python 3.13 or later:

```powershell
python evals/run_evals.py
```

The script uses only the Python standard library. It exits with:

- `0` when all checks pass;
- `1` when at least one assertion fails; and
- `2` for an invalid scenario/harness invocation or the unimplemented live
  mode.

For machine-readable output:

```powershell
python evals/run_evals.py --json
```

A different compatible scenario file can be selected with
`--scenario-file path/to/scenarios.v1.json`. The runner validates the schema,
scenario IDs, contiguous turn numbering, supported check types, and the
long-horizon scenario's exact 51-turn requirement before running assertions.

To see how a future live adapter could be added, without making a network
request:

```powershell
python evals/run_evals.py --explain-live
```

`--mode live` is deliberately not implemented; it prints the same guidance,
returns exit code `2`, and produces no fabricated results.

## Execution model

For each turn, the harness:

1. retrieves context from memories persisted by earlier turns;
2. generates a fixed mock response according to `response_policy`;
3. evaluates that turn's declarative checks; and
4. applies the turn's explicit `memory_events`.

This response-before-update order mirrors a typical chat flow in which the
latest turn is extracted and persisted after the response is generated. The
`all_active_semantic` retrieval scope is used only by the final broad profile
recall in the 51-turn fixture; ordinary checks use deterministic lexical
matching over memory keys and text.

The human-readable report includes one `PASS`/`FAIL` line per check and a
numeric summary:

```text
passed=N failed=N total=N pass_rate=0.000
```

The JSON form exposes the same counts and individual check details for a CI
wrapper, while still identifying the mode as offline prompt-contract testing.

## Adding live evaluation later

A live implementation should be a separate, explicitly opt-in adapter rather
than changing the meaning of this suite. A safe integration path is:

1. Define an adapter with operations for ingesting a user turn, retrieving
   active context, and generating a response.
2. Replay the same user turns through the actual application and provider.
3. Use the scenario's expected facts and policy assertions as an independent
   evaluator; do not treat a model's self-reported memory as ground truth.
4. Capture provider/model/template versions, generation settings, failures,
   latency, and cost alongside each result.
5. Keep live output in a separate report from offline counts, and use only
   synthetic or redacted secrets.

Until that adapter exists, the only truthful result from this directory is the
repeatable offline contract result produced by the deterministic mock.
