#!/usr/bin/env python3
"""Parse quiz bank markdown and generate Canvas quizzes."""

import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Statement:
    """A single T/F statement in a quiz question."""
    text: str
    correct: bool
    explanation: str = ""


@dataclass
class Question:
    """A quiz question: scenario text + pool of T/F statements."""
    number: int
    title: str
    scenario: str
    statements: list[Statement] = field(default_factory=list)


def parse_quiz_bank(path: Path) -> list[Question]:
    """Parse a quiz bank markdown file into Question objects.

    Expected format:
        ## Question N: Title

        Scenario text (may span multiple lines/paragraphs).

        - [x] True statement
        - [ ] False statement
        ...

        ### Explanations

        - **True** — Explanation for first statement.
        - **False** — Explanation for second statement.
        ...

    Explanations are matched to statements by position (1st explanation
    goes with 1st statement, etc.). If a question has multiple checkbox
    blocks (e.g. Q4 with proton + electron parts), all checkboxes are
    collected in order and paired with all explanations in order across
    all ### Explanations sections.
    """
    content = path.read_text()
    questions = []

    # Split on ## Question headers
    parts = re.split(r'^## Question (\d+):\s*(.+)$', content, flags=re.MULTILINE)

    # parts[0] is preamble (before first question), then triples: (number, title, body)
    for i in range(1, len(parts), 3):
        number = int(parts[i])
        title = parts[i + 1].strip()
        body = parts[i + 2]

        # Split body into pre-explanation and explanation sections
        explanation_splits = re.split(r'^### Explanations?(?:\s.*)?$', body, flags=re.MULTILINE)
        checkbox_body = explanation_splits[0]

        # Parse all explanations from all ### Explanations sections
        explanations = []
        explanation_pattern = re.compile(
            r'^- \*\*(True|False)\*\*\s*[—–-]\s*(.+?)(?=\n- \*\*(?:True|False)\*\*|\n###|\n## |\Z)',
            re.MULTILINE | re.DOTALL,
        )
        for section in explanation_splits[1:]:
            for match in explanation_pattern.finditer(section):
                explanations.append(match.group(2).strip())

        # Extract checkbox statements from pre-explanation body
        statements = []
        checkbox_pattern = re.compile(r'^- \[([ xX])\] (.+)$', re.MULTILINE)

        for j, match in enumerate(checkbox_pattern.finditer(checkbox_body)):
            correct = match.group(1).lower() == 'x'
            text = match.group(2).strip()
            explanation = explanations[j] if j < len(explanations) else ""
            statements.append(Statement(text=text, correct=correct, explanation=explanation))

        # Scenario is everything before the first checkbox
        first_checkbox = checkbox_pattern.search(checkbox_body)
        scenario = checkbox_body[:first_checkbox.start()].strip() if first_checkbox else checkbox_body.strip()

        questions.append(Question(
            number=number,
            title=title,
            scenario=scenario,
            statements=statements,
        ))

    return questions


def sample_quiz(
    questions: list[Question],
    sample_size: int = 5,
    seed: int = None,
    question_numbers: list[int] = None,
    num_questions: int = None,
) -> list[tuple[Question, list[Statement]]]:
    """Sample a subset of statements from each question.

    Args:
        questions: Parsed question bank.
        sample_size: Number of statements to sample per question.
        seed: Random seed for reproducibility.
        question_numbers: If given, only include these question numbers.
        num_questions: If given, randomly select this many questions from
            the filtered pool before sampling statements.

    Returns:
        List of (question, sampled_statements) tuples.
    """
    rng = random.Random(seed)

    pool = [q for q in questions if not question_numbers or q.number in question_numbers]

    if num_questions is not None:
        pool = rng.sample(pool, min(num_questions, len(pool)))
        pool.sort(key=lambda q: q.number)

    result = []
    for q in pool:
        true_pool = [s for s in q.statements if s.correct]
        false_pool = [s for s in q.statements if not s.correct]

        n_true = min(math.ceil(sample_size / 2), len(true_pool))
        n_false = min(sample_size - n_true, len(false_pool))

        # If one pool is short, fill from the other
        deficit = sample_size - n_true - n_false
        if deficit > 0:
            n_true = min(n_true + deficit, len(true_pool))
            deficit = sample_size - n_true - n_false
        if deficit > 0:
            n_false = min(n_false + deficit, len(false_pool))

        sampled = rng.sample(true_pool, n_true) + rng.sample(false_pool, n_false)
        rng.shuffle(sampled)
        result.append((q, sampled))

    return result


def convert_text(text: str) -> str:
    """Convert inline LaTeX math to Canvas-compatible format.

    Converts $...$ to \\(...\\) and $$...$$ to \\[...\\].
    """
    # Protect display math first
    display_maths = []
    def save_display(m):
        display_maths.append(m.group(1))
        return f"%%DISPLAY_MATH_{len(display_maths) - 1}%%"
    text = re.sub(r'\$\$(.+?)\$\$', save_display, text, flags=re.DOTALL)

    # Then inline math
    inline_maths = []
    def save_inline(m):
        inline_maths.append(m.group(1))
        return f"%%INLINE_MATH_{len(inline_maths) - 1}%%"
    text = re.sub(r'\$(.+?)\$', save_inline, text)

    # Restore as Canvas format
    for i, m in enumerate(display_maths):
        text = text.replace(f"%%DISPLAY_MATH_{i}%%", f"\\[{m}\\]")
    for i, m in enumerate(inline_maths):
        text = text.replace(f"%%INLINE_MATH_{i}%%", f"\\({m}\\)")

    return text


def build_canvas_quiz_data(
    title: str,
    quiz_items: list[tuple[Question, list[Statement]]],
    description: str = "",
    points_per_statement: float = 0.1,
    due_at: str = None,
    published: bool = False,
    allowed_attempts: int = 1,
) -> tuple[dict, list[dict]]:
    """Build Canvas API payloads for quiz and questions.

    Each bank question becomes one multiple_answers_question with T/F
    checkboxes. Sampling enforces a fixed T/F ratio so the denominator
    (number of True answers) is consistent across questions.

    Returns:
        (quiz_data, list_of_question_data)
    """
    quiz_data = {
        "quiz[title]": title,
        "quiz[description]": convert_text(description),
        "quiz[quiz_type]": "assignment",
        "quiz[published]": str(published).lower(),
        "quiz[allowed_attempts]": str(allowed_attempts),
        "quiz[scoring_policy]": "keep_highest",
        "quiz[show_correct_answers]": "true",
        "quiz[show_correct_answers_last_attempt]": "true",
    }
    if due_at:
        quiz_data["quiz[due_at]"] = due_at

    question_payloads = []
    for q, statements in quiz_items:
        scenario_html = f"<p>{convert_text(q.scenario)}</p>"

        answers = []
        for stmt in statements:
            answer = {
                "answer_text": convert_text(stmt.text),
                "answer_weight": 100 if stmt.correct else 0,
            }
            if stmt.explanation:
                answer["answer_comment_html"] = convert_text(stmt.explanation)
            answers.append(answer)

        question_payloads.append({
            "question_name": q.title,
            "question_text": scenario_html,
            "question_type": "multiple_answers_question",
            "points_possible": points_per_statement * len(statements),
            "answers": answers,
        })

    return quiz_data, question_payloads
