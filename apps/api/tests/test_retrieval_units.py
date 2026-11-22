"""Unit tests for the retrieval logic that has no database.

These cover the parts where a silent bug costs accuracy: rank fusion, section
dedupe, and the citation label the evidence panel renders.
"""

from __future__ import annotations

from askdocs_api.retrieval import (
    Candidate,
    dedupe_by_section,
    infer_doc_scope,
    reciprocal_rank_fusion,
)


def make(chunk_id: str, section: str, doc_id: str = "it-act-1961") -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_title="Income-tax Act, 1961",
        doc_type="act",
        vintage="consolidated up to Finance Act, 2021",
        applies_to_ay="AY 2026-27 and earlier",
        section=section,
        section_title=f"Title of {section}",
        chapter="VI-A",
        page=330,
        text=f"text of {chunk_id}",
        chars=len(f"text of {chunk_id}"),
    )


def test_rrf_rewards_agreement_between_retrievers() -> None:
    """A chunk both retrievers like must outrank one only a single retriever likes."""
    dense = [make("a", "80C"), make("b", "80D")]
    lexical = [make("b", "80D"), make("c", "80CCD")]
    fused = reciprocal_rank_fusion(dense, lexical, k=60)
    assert fused[0].chunk_id == "b", "the chunk in both lists must rank first"
    assert [c.chunk_id for c in fused[1:]] == ["a", "c"]


def test_rrf_scores_are_rank_based_not_score_based() -> None:
    """Cosine and ts_rank are never compared; only positions are."""
    dense = [make("a", "80C")]
    lexical = [make("a", "80C")]
    fused = reciprocal_rank_fusion(dense, lexical, k=60)
    assert fused[0].scores["rrf"] == 2 / 61


def test_dedupe_keeps_one_chunk_per_section_first() -> None:
    ordered = [make(f"80C-{i}", "80C") for i in range(4)] + [make("80D-0", "80D")]
    selected = dedupe_by_section(ordered, top_k=2)
    assert [c.chunk_id for c in selected] == ["80C-0", "80D-0"]


def test_dedupe_fills_from_used_sections_when_context_is_short() -> None:
    """With only one section retrieved, a second chunk from it is better than nothing."""
    ordered = [make(f"80C-{i}", "80C") for i in range(3)]
    selected = dedupe_by_section(ordered, top_k=2)
    assert len(selected) == 2
    assert {c.section for c in selected} == {"80C"}


def test_dedupe_respects_top_k() -> None:
    ordered = [make(f"c{i}", f"s{i}") for i in range(10)]
    assert len(dedupe_by_section(ordered, top_k=6)) == 6


def test_label_is_the_citation_address() -> None:
    """`doc · section · chapter · page · vintage`, in that order (MASTER.md)."""
    label = make("80C-0", "80C").label
    assert label.startswith("Income-tax Act, 1961")
    assert "Section 80C" in label
    assert "Chapter VI-A" in label
    assert "p. 330" in label
    assert label.rstrip().endswith(")")
    assert label.index("Section") < label.index("Chapter") < label.index("p. 330")


def test_scope_inferred_from_the_act_a_question_names() -> None:
    """Asking about the 1961 Act must not retrieve 2025 chunks with the same number."""
    assert infer_doc_scope("Under the Income-tax Act, 1961, what is section 80C?") == [
        "it-act-1961"
    ]
    assert infer_doc_scope("What does the Income-tax Act, 2025 say about tax year?") == [
        "it-act-2025",
        "it-rules-2026",
    ]
    assert infer_doc_scope("What is the GST registration threshold?") == [
        "cgst-act-2017",
        "cgst-rules-2017",
    ]


def test_scope_is_none_when_the_question_names_no_instrument() -> None:
    """Unscoped search is the default; both Acts stay reachable."""
    assert infer_doc_scope("How much can I deduct for tuition fees?") is None
