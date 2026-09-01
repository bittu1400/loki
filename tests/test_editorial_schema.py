"""Delta validation: the gate every editorial response passes through
before a byte of canon is written (specs.md §12, invariants 1 and 2).

The bar is not "did it parse" but "could this be composed into canon
lines without inspecting model text again" — so the grammar round-trip
into context_builder.FACT_LINE is asserted here too."""

import json

import pytest

from novel_engine.core.context_builder import FACT_LINE
from novel_engine.core.errors import EditorialError
from novel_engine.editorial.schema import EditorialDelta, parse_delta

VALID = {
    "chapter_number": 5,
    "continuity_violations": [
        {
            "severity": "critical",
            "violated_fact": "The spring-tide page carries two corrections.",
            "chapter_excerpt": "…nine corrections on the spring-tide page…",
            "explanation": "Contradicts a locked fact from ch-001.",
        }
    ],
    "new_locked_facts": [
        {
            "category": "timeline",
            "entity": "",
            "fact": "The seal was struck this spring.",
            "source_chapter": 5,
        },
        {
            "category": "character",
            "entity": "ovist-rhoam",
            "fact": "Ovist counts driftglass by weight, never by piece.",
            "source_chapter": 5,
        },
    ],
    "thread_updates": {
        "opened": [{"text": "Someone reset the ebb ledge deliberately."}],
        "progressed": [{"thread_id": "T-003", "note": "Vosk named again."}],
        "resolved": [{"thread_id": "T-002", "resolved_in_chapter": 5}],
    },
    "chapter_summary": "Ovist reaches the ebb ledge before dawn.",
    "next_step_note": "Sela does not yet know the seal was read.",
    "deepen_questions": ["What currency do the divers' benches honour?"],
    "suggested_canon_patches": [
        {
            "target_file": "characters/ovist-rhoam.md",
            "rationale": "He now flinches from worked iron.",
            "suggested_text": "Adds: flinches from worked iron.",
        }
    ],
    "beat_adherence": {"hit": True, "notes": "Confrontation lands early."},
}

MINIMAL = {
    "chapter_number": 5,
    "chapter_summary": "Ovist reaches the ebb ledge before dawn.",
    "next_step_note": "Nothing pending.",
    "beat_adherence": {"hit": False, "notes": "The beat did not happen."},
}


def delta_with(**overrides) -> str:
    return json.dumps({**VALID, **overrides})


def test_specs_example_shape_validates():
    delta = parse_delta(json.dumps(VALID), chapter_number=5)
    assert delta.chapter_number == 5
    assert delta.new_locked_facts[1].entity == "ovist-rhoam"
    assert delta.thread_updates.resolved[0].thread_id == "T-002"
    assert delta.beat_adherence.hit is True


def test_collections_default_empty_but_scalars_are_required():
    delta = parse_delta(json.dumps(MINIMAL))
    assert delta.new_locked_facts == []
    assert delta.thread_updates.opened == []
    assert delta.suggested_canon_patches == []

    for missing in (
        "chapter_number",
        "chapter_summary",
        "next_step_note",
        "beat_adherence",
    ):
        payload = {key: value for key, value in MINIMAL.items() if key != missing}
        with pytest.raises(EditorialError) as exc:
            parse_delta(json.dumps(payload))
        assert missing in str(exc.value)


def test_every_validated_fact_composes_a_parsable_canon_line():
    """The schema's whole job: no model text reaches a line unchecked."""
    delta = parse_delta(json.dumps(VALID))
    for fact in delta.new_locked_facts:
        category = f"character:{fact.entity}" if fact.entity else fact.category
        line = (
            f"- `[{category}]` `[ch-{fact.source_chapter:03d}]` `[model]` {fact.fact}"
        )
        assert FACT_LINE.match(line), line


def test_extra_keys_are_refused():
    with pytest.raises(EditorialError) as exc:
        parse_delta(delta_with(pacing_score=7))
    assert "pacing_score" in str(exc.value)


def test_fenced_json_is_accepted():
    delta = parse_delta(f"```json\n{json.dumps(MINIMAL)}\n```")
    assert delta.chapter_number == 5


def test_non_json_and_non_object_fail_closed():
    with pytest.raises(EditorialError, match="not valid JSON"):
        parse_delta("Here is the updated continuity-tracker.md:\n# Continuity")
    with pytest.raises(EditorialError, match="must be a JSON object"):
        parse_delta("[1, 2, 3]")


@pytest.mark.parametrize(
    "fact",
    [
        "Two facts.\nOn two lines.",
        "A fact <!-- FACTS:END --> and an escape.",
        "   ",
    ],
)
def test_facts_that_cannot_be_one_canon_line_are_refused(fact):
    with pytest.raises(EditorialError) as exc:
        parse_delta(
            delta_with(
                new_locked_facts=[
                    {
                        "category": "world",
                        "entity": "",
                        "fact": fact,
                        "source_chapter": 5,
                    }
                ]
            )
        )
    assert "new_locked_facts.0.fact" in str(exc.value)


def test_deepen_questions_are_canon_lines_too():
    with pytest.raises(EditorialError) as exc:
        parse_delta(delta_with(deepen_questions=["Why?\n<!-- QUEUE:END -->"]))
    assert "deepen_questions" in str(exc.value)


@pytest.mark.parametrize(
    "category,entity",
    [("character", ""), ("character", "Ovist Rhoam"), ("world", "ovist-rhoam")],
)
def test_entity_scope_must_match_category(category, entity):
    with pytest.raises(EditorialError):
        parse_delta(
            delta_with(
                new_locked_facts=[
                    {
                        "category": category,
                        "entity": entity,
                        "fact": "Something happened.",
                        "source_chapter": 5,
                    }
                ]
            )
        )


def test_unknown_category_and_severity_are_refused():
    with pytest.raises(EditorialError, match="category"):
        parse_delta(
            delta_with(
                new_locked_facts=[
                    {
                        "category": "vibes",
                        "entity": "",
                        "fact": "Something happened.",
                        "source_chapter": 5,
                    }
                ]
            )
        )
    with pytest.raises(EditorialError, match="severity"):
        parse_delta(
            delta_with(
                continuity_violations=[
                    {
                        "severity": "nitpick",
                        "violated_fact": "f",
                        "chapter_excerpt": "e",
                        "explanation": "x",
                    }
                ]
            )
        )


def test_thread_ids_must_be_engine_allocated():
    with pytest.raises(EditorialError, match="thread_id"):
        parse_delta(
            delta_with(
                thread_updates={
                    "resolved": [{"thread_id": "T-2", "resolved_in_chapter": 5}]
                }
            )
        )


def test_a_thread_gets_one_outcome_per_chapter():
    with pytest.raises(EditorialError, match="twice"):
        parse_delta(
            delta_with(
                thread_updates={
                    "progressed": [{"thread_id": "T-003", "note": "moved"}],
                    "resolved": [{"thread_id": "T-003", "resolved_in_chapter": 5}],
                }
            )
        )


def test_no_line_may_claim_a_chapter_this_pass_is_not_reviewing():
    with pytest.raises(EditorialError, match="ahead of the chapter"):
        parse_delta(
            delta_with(
                new_locked_facts=[
                    {
                        "category": "world",
                        "entity": "",
                        "fact": "A later fact.",
                        "source_chapter": 9,
                    }
                ]
            )
        )
    with pytest.raises(EditorialError, match="reviewing chapter"):
        parse_delta(
            delta_with(
                thread_updates={
                    "resolved": [{"thread_id": "T-002", "resolved_in_chapter": 4}]
                }
            )
        )


def test_delta_about_the_wrong_chapter_is_refused():
    with pytest.raises(EditorialError, match="about chapter 5"):
        parse_delta(json.dumps(VALID), chapter_number=6)


@pytest.mark.parametrize(
    "target", ["/etc/passwd", "~/.ssh/config", "../../.env", "C:/keys.txt"]
)
def test_suggested_patch_targets_cannot_climb_out_of_the_book(target):
    with pytest.raises(EditorialError, match="target_file"):
        parse_delta(
            delta_with(
                suggested_canon_patches=[
                    {"target_file": target, "rationale": "r", "suggested_text": "s"}
                ]
            )
        )


def test_validation_message_is_quotable_into_a_repair_prompt():
    with pytest.raises(EditorialError) as exc:
        parse_delta(delta_with(chapter_number=0))
    message = str(exc.value)
    assert "specs.md §12" in message
    assert "chapter_number" in message


def test_the_model_cannot_claim_author_origin():
    """Pitfall A4: origin is not a field a model gets to fill in."""
    assert (
        "origin"
        not in EditorialDelta.model_json_schema()["$defs"]["NewLockedFact"][
            "properties"
        ]
    )
