import json
from pathlib import Path


CORPUS = Path("tests/fixtures/paraphrase_cases.json")


def test_paraphrase_corpus_covers_every_directive_and_required_language_forms() -> None:
    cases = json.loads(CORPUS.read_text())["cases"]
    expected = [item for case in cases for item in case["expected"]]
    notes = " ".join(note for case in cases for note in case["operator_notes"]).lower()

    assert len(expected) == 18
    assert {item["directive_type"] for item in expected} == {
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
    }
    assert "13:00" in notes
    assert "one in the afternoon until three" in notes
    assert "percent" in notes
    assert "one-fifth" in notes
    assert "four-fifths" in notes
