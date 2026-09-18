"""Optional paid OpenRouter evaluation against organizer public interpretations."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.config import get_settings
from app.llm.interpreter import DirectiveInterpreter
from app.llm.openrouter_client import LLMProviderError, OpenRouterClient
from app.models.request import OptimizeEnergyRequest


DEFAULT_CASES = Path("BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json")


async def run(path: Path, limit: int | None, case_id: str | None) -> int:
    cases = json.loads(path.read_text())["cases"]
    if case_id is not None:
        cases = [case for case in cases if case["id"] == case_id]
        if not cases:
            print(f"Unknown case: {case_id}")
            return 2
    if limit is not None:
        cases = cases[:limit]
    interpreter = DirectiveInterpreter(OpenRouterClient(get_settings()))
    passed = 0
    for case in cases:
        request = OptimizeEnergyRequest.model_validate(case["input"])
        started = time.perf_counter()
        try:
            actual = await interpreter.interpret(request)
        except LLMProviderError as exc:
            elapsed = time.perf_counter() - started
            print(f"{case['id']}: ERROR ({elapsed:.3f}s): {exc}")
            continue
        elapsed = time.perf_counter() - started
        expected = case["expected_output"]["directive_interpretation"]
        comparable_actual = [
            {
                "note_index": item.note_index,
                "applies": item.applies,
                "directive_type": item.directive_type.value,
                "structured_adjustment": (
                    item.structured_adjustment.model_dump()
                    if item.structured_adjustment is not None
                    else None
                ),
            }
            for item in actual
        ]
        comparable_expected = [
            {key: item[key] for key in comparable_actual[0]}
            for item in expected
        ]
        ok = comparable_actual == comparable_expected
        passed += ok
        print(f"{case['id']}: {'PASS' if ok else 'FAIL'} ({elapsed:.3f}s)")
        if not ok:
            print("  expected:", comparable_expected)
            print("  actual:  ", comparable_actual)
    print(f"Result: {passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case", dest="case_id")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.cases, args.limit, args.case_id)))


if __name__ == "__main__":
    main()
