from collections import Counter

from scripts.generate_user_questions import CATEGORY_TARGETS, generate_questions


def test_generates_3200_unique_categorized_questions() -> None:
    records = generate_questions()

    assert len(records) == 3200
    assert len({record["id"] for record in records}) == 3200
    assert len({record["question"] for record in records}) == 3200
    assert Counter(record["category"] for record in records) == Counter(CATEGORY_TARGETS)
