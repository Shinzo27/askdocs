"""The parts of Week 2 that must be right without a model.

Citation validation and the refusal gate decide whether an answer is publishable;
both are pure functions, so they are tested exhaustively rather than smoke-tested.
"""

from __future__ import annotations

from askdocs_api import sessions
from askdocs_api.citations import cited_sources, validate
from askdocs_api.prompts import Source, fit_budget
from askdocs_api.refusal import out_of_corpus_year, should_refuse


def source(marker: int, section: str = "80C", page: int = 330, text: str = "body") -> Source:
    return Source(
        marker=marker,
        chunk_id=f"it-act-1961:{section}:0",
        doc_id="it-act-1961",
        doc_title="Income-tax Act, 1961",
        section=section,
        section_title=f"Title of {section}",
        chapter="VI",
        page=page,
        vintage="consolidated up to Finance Act, 2021",
        text=text,
    )


# --- citation validation ---------------------------------------------------
def test_answer_without_markers_fails() -> None:
    check = validate("Section 80C allows a deduction of 1,50,000 rupees.", [source(1)])
    assert not check.valid
    assert check.reason == "no_markers"


def test_marker_outside_context_fails() -> None:
    """The model may only cite what it was given - this is the whole contract."""
    check = validate("The limit is 1,50,000 [3].", [source(1), source(2)])
    assert not check.valid
    assert check.reason == "marker_outside_context"
    assert check.unsupported == [3]


def test_valid_answer_keeps_its_text() -> None:
    check = validate("The ceiling under section 80C is 1,50,000 rupees [1].", [source(1)])
    assert check.valid
    assert check.markers == [1]
    assert check.stripped_sentences == 0
    assert "1,50,000" in check.text


def test_strict_mode_strips_uncited_claim_sentences() -> None:
    """A confident number with no citation is the failure mode this exists to stop."""
    answer = (
        "The 80C ceiling is 1,50,000 rupees [1]. "
        "You can also claim a separate eight per cent deduction under another scheme entirely."
    )
    check = validate(answer, [source(1)])
    assert check.valid
    assert check.stripped_sentences == 1
    assert "separate eight per cent deduction" not in check.text
    assert "1,50,000" in check.text


def test_uncited_prose_is_not_a_publishable_answer() -> None:
    """One sentence, no marker: the same failure as an empty answer, named clearly."""
    answer = "Deductions are available for many kinds of investment under the Act."
    check = validate(answer, [source(1)])
    assert not check.valid
    assert check.reason == "no_markers"


def test_cited_sources_returns_only_used_markers() -> None:
    sources = [source(1, "80C"), source(2, "80D"), source(3, "80E")]
    used = cited_sources("See 80C [1] and 80E [3].", sources)
    assert [s.section for s in used] == ["80C", "80E"]


# --- refusal gate ----------------------------------------------------------
def test_empty_retrieval_refuses() -> None:
    refusal = should_refuse("Anything?", [], 0.0)
    assert refusal is not None
    assert refusal.reason == "empty_retrieval"


def test_low_score_refuses() -> None:
    refusal = should_refuse("What is the tax on moon mining?", [source(1)], -3.0)
    assert refusal is not None
    assert refusal.reason == "low_score"
    assert "closest passages" in refusal.message


def test_out_of_corpus_year_refuses() -> None:
    assert out_of_corpus_year("What was the rate in 1850?") == 1850
    assert out_of_corpus_year("Rate for tax year 2027-28?") is None
    refusal = should_refuse("What was the rate in 1850?", [source(1)], 5.0)
    assert refusal is not None
    assert refusal.reason == "out_of_corpus_date"


def test_named_section_missing_refuses() -> None:
    """A question naming section 80C must not be answered from section 80E."""
    refusal = should_refuse("What does section 80C allow?", [source(1, "80E")], 4.0)
    assert refusal is not None
    assert refusal.reason == "no_section_match"


def test_named_section_present_answers() -> None:
    assert should_refuse("What does section 80C allow?", [source(1, "80C")], 4.0) is None


def test_good_retrieval_does_not_refuse() -> None:
    assert should_refuse("How much is the 80C deduction?", [source(1, "80C")], 3.2) is None


# --- context budget --------------------------------------------------------
def test_budget_drops_the_tail_never_the_head() -> None:
    sources = [source(i, text="x" * 5000) for i in range(1, 6)]
    kept = fit_budget(sources, budget_tokens=1500)  # ~6000 chars
    assert kept[0].marker == 1
    assert len(kept) < len(sources)
    assert [s.marker for s in kept] == list(range(1, len(kept) + 1))


# --- sessions --------------------------------------------------------------
def test_session_roundtrip_and_tamper() -> None:
    session_id, cookie = sessions.issue()
    assert sessions.verify(cookie) == session_id
    assert sessions.verify(cookie[:-2] + "ff") is None
    assert sessions.verify("garbage") is None
    assert sessions.verify(None) is None
