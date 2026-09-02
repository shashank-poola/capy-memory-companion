#!/usr/bin/env python3
"""Run the dependency-free companion-memory contract fixtures.

The default runner is intentionally deterministic. Scenario files provide the
structured memory events that stand in for extraction, and this file supplies
small mocked retrieval and response components. It does not call an LLM.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

type JsonObject = dict[str, object]
type JsonList = list[object]

DEFAULT_SCENARIO_PATH = Path(__file__).resolve().with_name("scenarios.v1.json")
EXPECTED_SCHEMA_VERSION = "1.0"
ALLOWED_RESPONSE_POLICIES = {
    "acknowledge",
    "memory",
    "secret_refusal",
    "unknown",
}
ALLOWED_RETRIEVAL_SCOPES = {"lexical", "all_active_semantic"}
KNOWN_CHECKS = {
    "active_contains",
    "active_count",
    "active_key_absent",
    "active_state",
    "all_retrieved_active",
    "blocked_sensitive_events",
    "inactive_contains",
    "inactive_state",
    "response_contains",
    "response_excludes",
    "retrieved_contains",
    "retrieved_count",
    "retrieved_first_is",
    "retrieved_has_keys",
    "retrieved_score_greater",
    "retrieved_second_is",
    "turn_count",
}
STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "am",
        "an",
        "and",
        "are",
        "do",
        "for",
        "i",
        "is",
        "me",
        "my",
        "of",
        "the",
        "to",
        "what",
        "where",
        "which",
        "you",
        "your",
    }
)
TOKEN_RE: re.Pattern[str] = re.compile(r"[a-z0-9]+")
SECRET_RE = re.compile(
    r"\b(password|passcode|secret|credential|access token|api key|private key)\b",
    re.IGNORECASE,
)

LIVE_GUIDANCE = """Live mode is not implemented by this harness.
No provider was contacted and no live results were produced.

A future live adapter should:
1. Expose the same operations used here: ingest a user turn, retrieve context,
   and generate a response.
2. Replay the scenario user turns through the configured application instead
   of applying the fixture's mock memory events directly.
3. Record provider, model, prompt/template version, temperature, and seed (if
   supported), then apply the same policy assertions independently of the
   model's prose.
4. Keep secrets synthetic or redacted, make network use opt-in, and report
   live results separately from this offline pass rate.
"""


class SuiteError(ValueError):
    """Raised when the versioned scenario contract is invalid."""


@dataclass(slots=True)
class MemoryRecord:
    """A small in-memory stand-in for a persisted memory row."""

    record_id: int
    key: str
    value: str
    text: str
    kind: str
    state: str
    active: bool
    occurred_at: datetime.datetime | None
    importance: float
    created_turn: int

    @property
    def searchable_text(self) -> str:
        return f"{self.key.replace('_', ' ')} {self.value} {self.text}"


@dataclass(frozen=True, slots=True)
class Retrieval:
    record: MemoryRecord
    score: float
    recency_multiplier: float


@dataclass(frozen=True, slots=True)
class CheckResult:
    scenario_id: str
    turn: int
    check_type: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class CliArguments:
    scenario_file: Path
    mode: str
    explain_live: bool
    as_json: bool



def object_value(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise SuiteError(f"{label} must be an object")
    return cast(JsonObject, value)



def list_value(value: object, label: str) -> JsonList:
    if not isinstance(value, list):
        raise SuiteError(f"{label} must be a list")
    return cast(JsonList, value)



def required_string(obj: JsonObject, key: str, label: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise SuiteError(f"{label}.{key} must be a non-empty string")
    return value



def optional_string(obj: JsonObject, key: str, default: str, label: str) -> str:
    value = obj.get(key, default)
    if not isinstance(value, str):
        raise SuiteError(f"{label}.{key} must be a string")
    return value



def required_int(obj: JsonObject, key: str, label: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SuiteError(f"{label}.{key} must be an integer")
    return value



def required_string_list(obj: JsonObject, key: str, label: str) -> list[str]:
    values = list_value(obj.get(key), f"{label}.{key}")
    strings: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            raise SuiteError(f"{label}.{key}[{index}] must be a non-empty string")
        strings.append(value)
    return strings



def parse_timestamp(raw: object, field_name: str) -> datetime.datetime:
    if not isinstance(raw, str) or not raw:
        raise SuiteError(f"{field_name} must be a non-empty ISO timestamp")
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SuiteError(f"{field_name} is not a valid ISO timestamp: {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)



def tokenize(text: str) -> set[str]:
    return {
        match.group(0)
        for match in TOKEN_RE.finditer(text.casefold())
        if match.group(0) not in STOP_WORDS
    }



def looks_sensitive(event: JsonObject) -> bool:
    if bool(event.get("sensitive", False)):
        return True
    key = str(event.get("key", ""))
    text = str(event.get("text", ""))
    return bool(SECRET_RE.search(f"{key.replace('_', ' ')} {text}"))


class DeterministicMemoryStore:
    """A deterministic memory lifecycle and retrieval double.

    Scenario ``memory_events`` are explicit mock extractor outputs. This class
    deliberately does not infer facts from the natural-language user field.
    """

    def __init__(self, as_of: datetime.datetime) -> None:
        self.as_of: datetime.datetime = as_of
        self.records: list[MemoryRecord] = []
        self.blocked_sensitive_count: int = 0
        self._next_record_id: int = 1

    def apply_events(self, events: object, turn_number: int) -> None:
        if events is None:
            return
        event_values = list_value(events, f"turn {turn_number}.memory_events")

        for event_value in event_values:
            event = object_value(event_value, f"turn {turn_number}.memory_event")
            op = event.get("op")
            if not isinstance(op, str) or op not in {"remember", "replace", "delete"}:
                raise SuiteError(
                    f"turn {turn_number}: unsupported memory operation {op!r}"
                )

            # Sensitive candidates are counted for observability, but their
            # text/value never enters the in-memory record collection.
            if looks_sensitive(event):
                self.blocked_sensitive_count += 1
                continue

            key = event.get("key")
            if not isinstance(key, str) or not key:
                raise SuiteError(f"turn {turn_number}: memory event key is required")

            matching_active = [
                record
                for record in self.records
                if record.active and record.key == key
            ]
            if op == "delete":
                for record in matching_active:
                    record.active = False
                continue
            if op == "replace":
                for record in matching_active:
                    record.active = False

            text = event.get("text")
            value = event.get("value")
            if not isinstance(text, str) or not text:
                raise SuiteError(f"turn {turn_number}: memory event text is required")
            if not isinstance(value, str) or not value:
                raise SuiteError(f"turn {turn_number}: memory event value is required")

            kind = event.get("kind", "semantic")
            if not isinstance(kind, str) or kind not in {"semantic", "episodic"}:
                raise SuiteError(f"turn {turn_number}: unsupported memory kind {kind!r}")
            state = event.get("state", "current")
            if not isinstance(state, str) or not state:
                raise SuiteError(f"turn {turn_number}: memory event state is required")

            occurred_at_raw = event.get("occurred_at")
            occurred_at = (
                parse_timestamp(occurred_at_raw, f"turn {turn_number}.occurred_at")
                if occurred_at_raw is not None
                else None
            )
            importance_raw = event.get("importance", 1.0)
            if isinstance(importance_raw, bool) or not isinstance(
                importance_raw, (int, float)
            ):
                raise SuiteError(f"turn {turn_number}: memory importance must be numeric")
            importance = float(importance_raw)
            if not math.isfinite(importance) or not 0.0 <= importance <= 1.0:
                raise SuiteError(
                    f"turn {turn_number}: memory importance must be between 0 and 1"
                )

            self.records.append(
                MemoryRecord(
                    record_id=self._next_record_id,
                    key=key,
                    value=value,
                    text=text,
                    kind=kind,
                    state=state,
                    active=True,
                    occurred_at=occurred_at,
                    importance=importance,
                    created_turn=turn_number,
                )
            )
            self._next_record_id += 1

    def active_records(self) -> list[MemoryRecord]:
        return [record for record in self.records if record.active]

    def inactive_records(self) -> list[MemoryRecord]:
        return [record for record in self.records if not record.active]

    def recency_multiplier(self, record: MemoryRecord) -> float:
        if record.kind != "episodic" or record.occurred_at is None:
            return 1.0
        age_seconds = max(0.0, (self.as_of - record.occurred_at).total_seconds())
        # Fixed 30-day exponential decay keeps recency checks repeatable.
        return math.exp(-age_seconds / (30.0 * 24.0 * 60.0 * 60.0))

    def retrieve(self, query: str, scope: str = "lexical") -> list[Retrieval]:
        if scope not in ALLOWED_RETRIEVAL_SCOPES:
            raise SuiteError(f"unsupported retrieval scope: {scope!r}")

        active = self.active_records()
        if scope == "all_active_semantic":
            return [
                Retrieval(
                    record=record,
                    score=1.0,
                    recency_multiplier=self.recency_multiplier(record),
                )
                for record in active
                if record.kind == "semantic"
            ]

        query_terms = tokenize(query)
        if not query_terms:
            return []

        matches: list[Retrieval] = []
        for record in active:
            overlap = query_terms & tokenize(record.searchable_text)
            if not overlap:
                continue
            lexical_score = len(overlap) / len(query_terms)
            recency = self.recency_multiplier(record)
            score = lexical_score * record.importance * recency
            matches.append(
                Retrieval(
                    record=record,
                    score=score,
                    recency_multiplier=recency,
                )
            )

        matches.sort(
            key=lambda item: (
                -item.score,
                -item.recency_multiplier,
                item.record.created_turn,
                item.record.record_id,
            )
        )
        return matches


class DeterministicResponder:
    """A fixed response double for policy assertions, not a quality model."""

    def reply(self, policy: str, retrieved: list[Retrieval]) -> str:
        if policy == "acknowledge":
            return "Deterministic mock acknowledgement."
        if policy == "unknown":
            return "I don't know that detail; it was not provided."
        if policy == "secret_refusal":
            return "I cannot reveal or retain secrets such as passwords or tokens."
        if policy == "memory":
            if not retrieved:
                return "I don't know that detail; it was not provided."
            remembered = " ".join(item.record.text for item in retrieved)
            return f"Deterministic mock recall: {remembered}"
        raise SuiteError(f"unsupported response policy: {policy!r}")



def find_retrieved(retrieved: list[Retrieval], text: str) -> Retrieval | None:
    expected = text.casefold()
    for item in retrieved:
        if expected in item.record.text.casefold():
            return item
    return None



def find_memory(records: list[MemoryRecord], text: str) -> MemoryRecord | None:
    expected = text.casefold()
    for record in records:
        if expected in record.text.casefold():
            return record
    return None



def evaluate_check(
    scenario_id: str,
    turn_number: int,
    check: JsonObject,
    retrieved: list[Retrieval],
    response: str,
    store: DeterministicMemoryStore,
    scenario_turn_count: int,
) -> CheckResult:
    check_type = required_string(check, "type", "check")
    if check_type not in KNOWN_CHECKS:
        raise SuiteError(f"unknown check type: {check_type!r}")

    def result(passed: bool, detail: str) -> CheckResult:
        return CheckResult(scenario_id, turn_number, check_type, passed, detail)

    if check_type == "retrieved_count":
        expected = required_int(check, "count", "check")
        passed = len(retrieved) == expected
        return result(passed, f"retrieved={len(retrieved)} expected={expected}")

    if check_type == "retrieved_first_is":
        expected = required_string(check, "text", "check")
        actual = retrieved[0].record.text if retrieved else None
        detail = f"first={actual!r}; expected={expected!r}"
        return result(actual == expected, detail)

    if check_type == "retrieved_second_is":
        expected = required_string(check, "text", "check")
        actual = retrieved[1].record.text if len(retrieved) > 1 else None
        detail = f"second={actual!r}; expected={expected!r}"
        return result(actual == expected, detail)

    if check_type == "retrieved_contains":
        expected = required_string(check, "text", "check")
        match = find_retrieved(retrieved, expected)
        return result(match is not None, f"found={match is not None} text={expected!r}")

    if check_type == "retrieved_score_greater":
        higher_text = required_string(check, "higher_text", "check")
        lower_text = required_string(check, "lower_text", "check")
        higher = find_retrieved(retrieved, higher_text)
        lower = find_retrieved(retrieved, lower_text)
        passed = higher is not None and lower is not None and higher.score > lower.score
        if higher is None or lower is None:
            detail = (
                "both memories must be retrieved; "
                f"higher={higher is not None} lower={lower is not None}"
            )
        else:
            detail = f"higher_score={higher.score:.6f} lower_score={lower.score:.6f}"
        return result(passed, detail)

    if check_type == "retrieved_has_keys":
        expected_keys = set(required_string_list(check, "keys", "check"))
        actual_keys = {item.record.key for item in retrieved}
        missing = sorted(expected_keys - actual_keys)
        return result(not missing, f"missing_keys={missing}")

    if check_type == "all_retrieved_active":
        inactive = [item.record.record_id for item in retrieved if not item.record.active]
        return result(not inactive, f"inactive_record_ids={inactive}")

    if check_type == "response_contains":
        expected = required_string(check, "text", "check")
        passed = expected.casefold() in response.casefold()
        return result(passed, f"contains={passed} text={expected!r}")

    if check_type == "response_excludes":
        expected = required_string(check, "text", "check")
        passed = expected.casefold() not in response.casefold()
        return result(passed, f"excluded={passed} text={expected!r}")

    if check_type == "active_contains":
        expected = required_string(check, "text", "check")
        match = find_memory(store.active_records(), expected)
        return result(match is not None, f"found={match is not None} text={expected!r}")

    if check_type == "inactive_contains":
        expected = required_string(check, "text", "check")
        match = find_memory(store.inactive_records(), expected)
        return result(match is not None, f"found={match is not None} text={expected!r}")

    if check_type in {"active_state", "inactive_state"}:
        key = required_string(check, "key", "check")
        expected_state = required_string(check, "state", "check")
        records = (
            store.active_records()
            if check_type == "active_state"
            else store.inactive_records()
        )
        states = [record.state for record in records if record.key == key]
        passed = expected_state in states
        detail = f"key={key!r} states={states!r}; expected={expected_state!r}"
        return result(passed, detail)

    if check_type == "active_key_absent":
        key = required_string(check, "key", "check")
        active_keys = {record.key for record in store.active_records()}
        passed = key not in active_keys
        return result(passed, f"active_key_present={key in active_keys} key={key!r}")

    if check_type == "active_count":
        expected = required_int(check, "count", "check")
        actual = len(store.active_records())
        return result(actual == expected, f"active={actual} expected={expected}")

    if check_type == "blocked_sensitive_events":
        expected = required_int(check, "count", "check")
        actual = store.blocked_sensitive_count
        return result(actual == expected, f"blocked={actual} expected={expected}")

    if check_type == "turn_count":
        expected = required_int(check, "count", "check")
        return result(
            scenario_turn_count == expected,
            f"turns={scenario_turn_count} expected={expected}",
        )

    # KNOWN_CHECKS and the branches above should stay in sync.
    raise SuiteError(f"unhandled check type: {check_type!r}")



def validate_scenario(scenario_value: object) -> JsonObject:
    scenario = object_value(scenario_value, "scenario")
    scenario_id = required_string(scenario, "id", "scenario")
    _ = required_string(scenario, "title", f"scenario {scenario_id!r}")
    category = required_string(scenario, "category", f"scenario {scenario_id!r}")
    evaluation_layer = required_string(
        scenario, "evaluation_layer", f"scenario {scenario_id!r}"
    )
    if evaluation_layer != "prompt-contract":
        raise SuiteError(
            f"scenario {scenario_id!r} must use evaluation_layer 'prompt-contract'"
        )

    turns = list_value(scenario.get("turns"), f"scenario {scenario_id!r}.turns")
    if not turns:
        raise SuiteError(f"scenario {scenario_id!r} must have non-empty turns")
    for expected_turn, turn_value in enumerate(turns, start=1):
        turn = object_value(turn_value, f"scenario {scenario_id!r} turn")
        actual_turn = required_int(turn, "turn", f"scenario {scenario_id!r} turn")
        if actual_turn != expected_turn:
            raise SuiteError(
                f"scenario {scenario_id!r} turn numbering must be contiguous; expected {expected_turn}, got {actual_turn}"
            )
        _ = required_string(
            turn, "user", f"scenario {scenario_id!r} turn {actual_turn}"
        )
        policy = optional_string(
            turn,
            "response_policy",
            "acknowledge",
            f"scenario {scenario_id!r} turn {actual_turn}",
        )
        if policy not in ALLOWED_RESPONSE_POLICIES:
            raise SuiteError(
                f"scenario {scenario_id!r} turn {actual_turn} has unsupported response policy {policy!r}"
            )
        scope = optional_string(
            turn,
            "retrieval_scope",
            "lexical",
            f"scenario {scenario_id!r} turn {actual_turn}",
        )
        if scope not in ALLOWED_RETRIEVAL_SCOPES:
            raise SuiteError(
                f"scenario {scenario_id!r} turn {actual_turn} has unsupported retrieval scope {scope!r}"
            )
        checks = list_value(
            turn.get("checks", []),
            f"scenario {scenario_id!r} turn {actual_turn}.checks",
        )
        for check_value in checks:
            check = object_value(
                check_value,
                f"scenario {scenario_id!r} turn {actual_turn}.check",
            )
            check_type = required_string(
                check, "type", f"scenario {scenario_id!r} turn {actual_turn}.check"
            )
            if check_type not in KNOWN_CHECKS:
                raise SuiteError(
                    f"scenario {scenario_id!r} turn {actual_turn} has an unknown check"
                )

    if category == "long-horizon-persona":
        expected_count = scenario.get("expected_turn_count")
        if expected_count != 51 or len(turns) != 51:
            raise SuiteError(
                f"scenario {scenario_id!r} must contain exactly 51 turns"
            )
    return scenario



def load_suite(path: Path) -> tuple[JsonObject, datetime.datetime]:
    try:
        raw_value: object = cast(
            object, json.loads(path.read_text(encoding="utf-8"))
        )
    except FileNotFoundError as exc:
        raise SuiteError(f"scenario file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SuiteError(f"scenario file is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise SuiteError(f"could not read scenario file {path}: {exc}") from exc

    raw = object_value(raw_value, "scenario file root")
    schema_version = required_string(raw, "schema_version", "scenario file")
    if schema_version != EXPECTED_SCHEMA_VERSION:
        raise SuiteError(
            f"unsupported schema_version {schema_version!r}; expected {EXPECTED_SCHEMA_VERSION!r}"
        )

    scenario_values = list_value(raw.get("scenarios"), "scenario file.scenarios")
    if not scenario_values:
        raise SuiteError("scenario file must contain a non-empty scenarios list")

    seen_ids: set[str] = set()
    for scenario_value in scenario_values:
        scenario = validate_scenario(scenario_value)
        scenario_id = required_string(scenario, "id", "scenario")
        if scenario_id in seen_ids:
            raise SuiteError(f"duplicate scenario id: {scenario_id!r}")
        seen_ids.add(scenario_id)

    as_of = parse_timestamp(raw.get("as_of"), "suite.as_of")
    return raw, as_of



def run_suite(
    suite: JsonObject, suite_as_of: datetime.datetime
) -> list[CheckResult]:
    results: list[CheckResult] = []
    scenario_values = list_value(suite.get("scenarios"), "scenario file.scenarios")
    for scenario_value in scenario_values:
        scenario = object_value(scenario_value, "scenario")
        scenario_id = required_string(scenario, "id", "scenario")
        scenario_as_of_raw = scenario.get("as_of")
        scenario_as_of = (
            parse_timestamp(scenario_as_of_raw, f"scenario {scenario_id}.as_of")
            if scenario_as_of_raw is not None
            else suite_as_of
        )
        store = DeterministicMemoryStore(scenario_as_of)
        responder = DeterministicResponder()
        turns = list_value(scenario.get("turns"), f"scenario {scenario_id}.turns")

        for turn_value in turns:
            turn = object_value(turn_value, f"scenario {scenario_id}.turn")
            turn_number = required_int(turn, "turn", f"scenario {scenario_id}.turn")
            query = optional_string(
                turn, "query", "", f"scenario {scenario_id} turn {turn_number}"
            )
            policy = optional_string(
                turn,
                "response_policy",
                "acknowledge",
                f"scenario {scenario_id} turn {turn_number}",
            )
            scope = optional_string(
                turn,
                "retrieval_scope",
                "lexical",
                f"scenario {scenario_id} turn {turn_number}",
            )
            retrieved = store.retrieve(query, scope)
            response = responder.reply(policy, retrieved)
            checks = list_value(
                turn.get("checks", []),
                f"scenario {scenario_id} turn {turn_number}.checks",
            )
            for check_value in checks:
                check = object_value(
                    check_value,
                    f"scenario {scenario_id} turn {turn_number}.check",
                )
                results.append(
                    evaluate_check(
                        scenario_id=scenario_id,
                        turn_number=turn_number,
                        check=check,
                        retrieved=retrieved,
                        response=response,
                        store=store,
                        scenario_turn_count=len(turns),
                    )
                )

            # The production flow responds from existing context before the
            # latest turn's extraction/update phase is persisted.
            store.apply_events(turn.get("memory_events", []), turn_number)
    return results



def result_summary(results: list[CheckResult]) -> dict[str, int | float]:
    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed
    total = len(results)
    return {
        "passed": passed,
        "failed": failed,
        "total": total,
        "pass_rate": passed / total if total else 0.0,
    }



def serialize_result(result: CheckResult) -> JsonObject:
    return {
        "scenario_id": result.scenario_id,
        "turn": result.turn,
        "check_type": result.check_type,
        "passed": result.passed,
        "detail": result.detail,
    }



def print_human_results(
    results: list[CheckResult], scenario_path: Path, scenario_count: int
) -> None:
    summary = result_summary(results)
    print("Capy companion-memory evaluation")
    print("mode=offline-deterministic-prompt-contract")
    print(f"scenario_file={scenario_path}")
    print(f"scenarios={scenario_count}")
    print()
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.scenario_id} turn={result.turn} check={result.check_type}: {result.detail}")
    print()
    print(f"passed={summary['passed']} failed={summary['failed']} total={summary['total']} pass_rate={summary['pass_rate']:.3f}")



def print_json_results(
    results: list[CheckResult], scenario_path: Path, scenario_count: int
) -> None:
    payload: JsonObject = {
        "mode": "offline-deterministic-prompt-contract",
        "scenario_file": str(scenario_path),
        "scenarios": scenario_count,
        **result_summary(results),
        "results": [serialize_result(result) for result in results],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic companion-memory prompt-contract checks."
    )
    _ = parser.add_argument(
        "--scenario-file",
        type=Path,
        default=DEFAULT_SCENARIO_PATH,
        help="Versioned JSON scenario file (default: evals/scenarios.v1.json).",
    )
    _ = parser.add_argument(
        "--mode",
        choices=("offline", "live"),
        default="offline",
        help="offline is implemented; live is intentionally not executed.",
    )
    _ = parser.add_argument(
        "--explain-live",
        action="store_true",
        help="Explain a safe future live adapter without running one.",
    )
    _ = parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON results.",
    )
    return parser



def namespace_value(namespace: argparse.Namespace, name: str) -> object:
    return cast(object, getattr(namespace, name))



def parse_arguments(argv: list[str] | None = None) -> CliArguments:
    namespace = build_parser().parse_args(argv)
    scenario_file_value = namespace_value(namespace, "scenario_file")
    if not isinstance(scenario_file_value, Path):
        raise SuiteError("--scenario-file did not produce a path")
    mode_value = namespace_value(namespace, "mode")
    if not isinstance(mode_value, str):
        raise SuiteError("--mode did not produce a string")
    explain_live_value = namespace_value(namespace, "explain_live")
    as_json_value = namespace_value(namespace, "as_json")
    if not isinstance(explain_live_value, bool) or not isinstance(as_json_value, bool):
        raise SuiteError("boolean command-line options did not produce booleans")
    return CliArguments(
        scenario_file=scenario_file_value,
        mode=mode_value,
        explain_live=explain_live_value,
        as_json=as_json_value,
    )



def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_arguments(argv)
    except SuiteError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.explain_live:
        print(LIVE_GUIDANCE)
        return 0
    if args.mode == "live":
        print(LIVE_GUIDANCE, file=sys.stderr)
        return 2

    try:
        suite, suite_as_of = load_suite(args.scenario_file)
        results = run_suite(suite, suite_as_of)
    except SuiteError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    scenario_count = len(list_value(suite.get("scenarios"), "scenario file.scenarios"))
    if args.as_json:
        print_json_results(results, args.scenario_file, scenario_count)
    else:
        print_human_results(results, args.scenario_file, scenario_count)
    return 0 if results and all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
