from app.routing import IntentPrediction, SemanticRouter


class StubClassifier:
    def __init__(self, prediction: IntentPrediction):
        self.prediction = prediction

    def classify_intent(self, message: str) -> IntentPrediction:
        return self.prediction


def test_semantic_router_handles_meaning_without_fixed_keywords() -> None:
    router = SemanticRouter(StubClassifier(IntentPrediction(
        intent="formal_appeal",
        confidence=0.91,
        reason="多次处理后问题仍未解决",
    )))

    decision = router.classify("拿回来处理过好多回了，结果用一天又出毛病")

    assert decision.route == "appeal"
    assert decision.source == "llm"
    assert decision.reason == "多次处理后问题仍未解决"


def test_high_certainty_policy_rule_skips_low_confidence_model_result() -> None:
    router = SemanticRouter(StubClassifier(IntentPrediction(
        intent="refund_request",
        confidence=0.4,
        reason="不确定",
    )))

    decision = router.classify("我不想退款，只想了解退款政策")

    assert decision.intent == "policy_question"
    assert decision.route == "service"
    assert decision.source == "deterministic_rule"


def test_deterministic_risk_rule_overrides_model() -> None:
    router = SemanticRouter(StubClassifier(IntentPrediction(
        intent="product_question",
        confidence=0.99,
        reason="商品咨询",
    )))

    decision = router.classify("充电器发生漏电，我该怎么办")

    assert decision.route == "risk"
    assert decision.source == "safety_rule"


class CountingClassifier(StubClassifier):
    def __init__(self, prediction: IntentPrediction):
        super().__init__(prediction)
        self.calls = 0

    def classify_intent(self, message: str) -> IntentPrediction:
        self.calls += 1
        return super().classify_intent(message)


def test_high_certainty_order_rule_skips_model() -> None:
    classifier = CountingClassifier(IntentPrediction("formal_appeal", 0.99, route="appeal"))
    router = SemanticRouter(classifier)

    decision = router.classify("查询订单 XY12345678 的物流")

    assert decision.intent == "shipment_query"
    assert decision.source == "deterministic_rule"
    assert classifier.calls == 0


def test_model_multi_intent_conflict_requests_clarification() -> None:
    router = SemanticRouter(StubClassifier(IntentPrediction(
        intent="shipment_query",
        route="service",
        confidence=0.84,
        candidate_intents=("refund_request",),
        requires_clarification=True,
        clarification_question="你希望先查询物流，还是先申请退款？",
    )))

    decision = router.classify("东西还没到，我也在考虑不要了")

    assert decision.route == "clarify"
    assert decision.source == "llm_clarification"
    assert decision.clarification_question == "你希望先查询物流，还是先申请退款？"


def test_low_confidence_normal_intent_requests_clarification() -> None:
    router = SemanticRouter(StubClassifier(IntentPrediction(
        intent="product_question",
        route="service",
        confidence=0.42,
        reason="信息不足",
    )))

    decision = router.classify("这个怎么办")

    assert decision.route == "clarify"
    assert decision.source == "low_confidence"


def test_low_confidence_risk_intent_requires_human_review() -> None:
    router = SemanticRouter(StubClassifier(IntentPrediction(
        intent="risk_report",
        route="risk",
        confidence=0.51,
        reason="可能涉及安全问题",
    )))

    decision = router.classify("用着有点不太对劲，但说不清楚")

    assert decision.route == "handoff"
    assert decision.source == "risk_guard"


def test_classifier_failure_falls_back_to_keywords() -> None:
    class FailingClassifier:
        def classify_intent(self, message: str) -> IntentPrediction:
            raise ValueError("invalid model output")

    decision = SemanticRouter(FailingClassifier()).classify("我要退款")

    assert decision.route == "aftersales"
    assert decision.source == "rule_fallback"
    assert "模型输出不可用" in decision.reason
