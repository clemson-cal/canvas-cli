"""Tests for quiz-bank parsing, sampling, and Canvas payload generation."""

from canvas_auto_quiz import parse_quiz_bank, sample_quiz, build_canvas_quiz_data
from canvas_auto_quiz.quiz import convert_text

BANK = """\
# Quiz bank

## Question 1: Gauss's law

A point charge $q$ sits at the center of a cube of side $L$.

- [x] The total flux equals $4\\pi q$.
- [x] The flux through one face is one sixth of the total.
- [ ] The flux depends on $L$.
- [ ] Moving the charge off-center changes the total flux.

### Explanations

- **True** — Gauss's law gives $4\\pi q_{enc}$.
- **True** — By symmetry each face sees an equal share.
- **False** — Enclosed charge is all that matters.
- **False** — Total flux depends only on enclosed charge.

## Question 2: Units

Consider Gaussian units.

- [x] Charge has units of statC.
- [ ] Charge has units of coulombs.
"""


def write_bank(tmp_path):
    path = tmp_path / "bank.md"
    path.write_text(BANK)
    return path


def test_parse_quiz_bank(tmp_path):
    questions = parse_quiz_bank(write_bank(tmp_path))
    assert len(questions) == 2
    q1 = questions[0]
    assert q1.number == 1
    assert q1.title == "Gauss's law"
    assert "point charge" in q1.scenario
    assert len(q1.statements) == 4
    assert [s.correct for s in q1.statements] == [True, True, False, False]
    assert q1.statements[0].explanation.startswith("Gauss's law")
    q2 = questions[1]
    assert len(q2.statements) == 2
    assert q2.statements[0].explanation == ""


def test_sample_quiz_is_seeded_and_balanced(tmp_path):
    questions = parse_quiz_bank(write_bank(tmp_path))
    items_a = sample_quiz(questions, sample_size=4, seed=42, question_numbers=[1])
    items_b = sample_quiz(questions, sample_size=4, seed=42, question_numbers=[1])
    assert len(items_a) == 1
    _, sampled = items_a[0]
    assert len(sampled) == 4
    # Balanced: half true, half false
    assert sum(s.correct for s in sampled) == 2
    # Same seed reproduces the same sample and order
    assert [s.text for s in items_a[0][1]] == [s.text for s in items_b[0][1]]


def test_build_canvas_quiz_data(tmp_path):
    questions = parse_quiz_bank(write_bank(tmp_path))
    items = sample_quiz(questions, sample_size=2, seed=1)
    quiz_data, payloads = build_canvas_quiz_data(
        title="Quiz 1",
        quiz_items=items,
        points_per_statement=0.5,
        due_at="2026-02-14T14:00:00",
        published=True,
        allowed_attempts=2,
    )
    assert quiz_data["quiz[title]"] == "Quiz 1"
    assert quiz_data["quiz[published]"] == "true"
    assert quiz_data["quiz[allowed_attempts]"] == "2"
    assert quiz_data["quiz[due_at]"] == "2026-02-14T14:00:00"
    assert len(payloads) == 2
    for qp in payloads:
        assert qp["question_type"] == "multiple_answers_question"
        assert qp["points_possible"] == 0.5 * len(qp["answers"])
        for ans in qp["answers"]:
            assert ans["answer_weight"] in (0, 100)


def test_convert_text_math_delimiters():
    assert convert_text("flux $4\\pi q$ here") == "flux \\(4\\pi q\\) here"
    assert convert_text("$$E = mc^2$$") == "\\[E = mc^2\\]"


def test_delivery_defaults_are_off(tmp_path):
    questions = parse_quiz_bank(write_bank(tmp_path))
    items = sample_quiz(questions, sample_size=2, seed=1)
    quiz_data, _ = build_canvas_quiz_data(title="Q", quiz_items=items)
    assert quiz_data["quiz[one_question_at_a_time]"] == "false"
    assert quiz_data["quiz[shuffle_answers]"] == "false"
    for absent in ("quiz[unlock_at]", "quiz[lock_at]", "quiz[time_limit]",
                   "quiz[access_code]", "quiz[cant_go_back]"):
        assert absent not in quiz_data


def test_in_class_delivery_fields(tmp_path):
    questions = parse_quiz_bank(write_bank(tmp_path))
    items = sample_quiz(questions, sample_size=2, seed=1)
    quiz_data, _ = build_canvas_quiz_data(
        title="Quiz 1",
        quiz_items=items,
        unlock_at="2026-09-08T14:10:00",
        lock_at="2026-09-08T14:18:00",
        time_limit=8,
        access_code="ricci",
        one_question_at_a_time=True,
        cant_go_back=True,
        shuffle_answers=True,
    )
    assert quiz_data["quiz[unlock_at]"] == "2026-09-08T14:10:00"
    assert quiz_data["quiz[lock_at]"] == "2026-09-08T14:18:00"
    assert quiz_data["quiz[time_limit]"] == "8"
    assert quiz_data["quiz[access_code]"] == "ricci"
    assert quiz_data["quiz[one_question_at_a_time]"] == "true"
    assert quiz_data["quiz[cant_go_back]"] == "true"
    assert quiz_data["quiz[shuffle_answers]"] == "true"


def test_cant_go_back_omitted_unless_one_at_a_time(tmp_path):
    """Canvas ignores cant_go_back on an all-at-once quiz; don't send a lie."""
    questions = parse_quiz_bank(write_bank(tmp_path))
    items = sample_quiz(questions, sample_size=2, seed=1)
    quiz_data, _ = build_canvas_quiz_data(
        title="Q", quiz_items=items, cant_go_back=True, one_question_at_a_time=False,
    )
    assert "quiz[cant_go_back]" not in quiz_data


def test_time_limit_zero_is_sent(tmp_path):
    """0 is a real value (no limit), distinct from 'unset' — must not be dropped."""
    questions = parse_quiz_bank(write_bank(tmp_path))
    items = sample_quiz(questions, sample_size=2, seed=1)
    quiz_data, _ = build_canvas_quiz_data(title="Q", quiz_items=items, time_limit=0)
    assert quiz_data["quiz[time_limit]"] == "0"
