"""Paid semantic evaluation over an internal paraphrase corpus."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.config import get_settings
from app.llm.interpreter import DirectiveInterpreter
from app.llm.openrouter_client import LLMProviderError, OpenRouterClient
from app.models.request import OptimizeEnergyRequest


DEFAULT_CORPUS = Path("tests/fixtures/paraphrase_cases.json")
PUBLIC_CASES = Path("BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json")


def _adjustment(item) -> dict | None:
    return item.structured_adjustment.model_dump() if item.structured_adjustment else None


async def run(corpus_path: Path, case_id: str | None) -> int:
    corpus = json.loads(corpus_path.read_text())["cases"]
    if case_id is not None:
        corpus = [case for case in corpus if case["id"] == case_id]
        if not corpus:
            print(f"Unknown case: {case_id}")
            return 2
    base = json.loads(PUBLIC_CASES.read_text())["cases"][0]["input"]
    interpreter = DirectiveInterpreter(OpenRouterClient(get_settings()))
    metrics = {name: 0 for name in ("relevance", "type", "hours", "numeric", "shape", "exact")}
    total = 0

    for case in corpus:
        payload = {**base, "scenario_id": case["id"], "operator_notes": case["operator_notes"]}
        started = time.perf_counter()
        try:
            actual = await interpreter.interpret(OptimizeEnergyRequest.model_validate(payload))
        except LLMProviderError as exc:
            print(f"{case['id']}: ERROR ({time.perf_counter() - started:.3f}s): {exc}")
            total += len(case["expected"])
            continue

        passed = 0
        for observed, expected in zip(actual, case["expected"], strict=True):
            total += 1
            observed_adjustment = _adjustment(observed)
            expected_adjustment = expected["structured_adjustment"]
            checks = {
                "relevance": observed.applies == expected["applies"],
                "type": observed.directive_type.value == expected["directive_type"],
                "shape": (
                    observed_adjustment is None and expected_adjustment is None
                ) or (
                    observed_adjustment is not None
                    and expected_adjustment is not None
                    and observed_adjustment.keys() == expected_adjustment.keys()
                ),
                "hours": (
                    observed_adjustment is None and expected_adjustment is None
                ) or (
                    observed_adjustment is not None
                    and expected_adjustment is not None
                    and observed_adjustment.get("hours") == expected_adjustment.get("hours")
                ),
                "numeric": True,
            }
            if expected_adjustment is not None:
                for key, value in expected_adjustment.items():
                    if key != "hours":
                        actual_value = (observed_adjustment or {}).get(key)
                        checks["numeric"] &= (
                            isinstance(actual_value, int | float)
                            and abs(actual_value - value) <= 0.01
                        )
            for name, ok in checks.items():
                metrics[name] += int(ok)
            exact = all(checks.values())
            metrics["exact"] += int(exact)
            passed += int(exact)
        elapsed = time.perf_counter() - started
        print(f"{case['id']}: {passed}/{len(case['expected'])} exact ({elapsed:.3f}s)")

    print(f"Result: {metrics['exact']}/{total} notes exact")
    for name in ("relevance", "type", "hours", "numeric", "shape"):
        print(f"{name}: {metrics[name]}/{total} ({100 * metrics[name] / total:.1f}%)")
    return 0 if metrics["exact"] == total else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--case", dest="case_id")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.corpus, args.case_id)))


if __name__ == "__main__":
    main()
