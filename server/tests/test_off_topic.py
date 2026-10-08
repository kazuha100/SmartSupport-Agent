from app.off_topic import OffTopicGuard, classify_message


def test_message_classification_is_conservative_for_support_questions() -> None:
    assert classify_message("P-C3 支持防水吗？") == "business"
    assert classify_message("这个耳机碰到水会坏吗？") == "business"
    assert classify_message("你好") == "neutral"
    assert classify_message("帮我写一段 Python 排序代码") == "off_topic"


def test_guard_blocks_after_limit_and_business_question_resets() -> None:
    guard = OffTopicGuard(max_allowed=2, window_seconds=1800)

    assert guard.check("user-1", "session-1", "讲个笑话").blocked is False
    assert guard.check("user-1", "session-1", "帮我写作业").blocked is False
    decision = guard.check("user-1", "session-1", "今天天气怎么样")
    assert decision.blocked is True
    assert decision.count == 3

    assert guard.check("user-1", "session-1", "查询订单 XY20260701").category == "business"
    assert guard.check("user-1", "session-1", "再讲个笑话").count == 1


def test_guard_isolates_sessions_and_does_not_count_greetings() -> None:
    guard = OffTopicGuard(max_allowed=1, window_seconds=1800)

    guard.check("user-1", "session-1", "讲个笑话")
    assert guard.check("user-1", "session-1", "你好").blocked is False
    assert guard.check("user-1", "session-2", "帮我写作业").blocked is False
    assert guard.check("user-1", "session-1", "帮我写作业").blocked is True
