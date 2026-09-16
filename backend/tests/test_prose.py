import pytest

from app.llm.prose import humanize_codes


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        # The row that shipped.
        ("No postoperative data reported · risk missing_data",
         "No postoperative data reported · not enough data to assess risk"),
        ("Pain worsening · risk high", "Pain worsening · high risk"),
        ("risk: medium this week", "medium risk this week"),
        # Reason codes the engine emits, echoed in a sentence.
        ("Flagged for COMPOSITE_HIGH and STEPS_FALLING", "Flagged for composite high and steps falling"),
        ("status missing_data", "status missing data"),
    ],
)
def test_engine_codes_become_words(raw: str, clean: str) -> None:
    assert humanize_codes(raw) == clean


@pytest.mark.parametrize(
    "text",
    [
        "Recovery tracking as expected",
        "Pain worsening 4 days · feverish night · RHR 73 (+9) vs baseline",
        "At risk of falling behind the expected curve",  # "risk" not followed by a tier
        "",
    ],
)
def test_ordinary_prose_is_untouched(text: str) -> None:
    assert humanize_codes(text) == text
