from dataclasses import dataclass, field
import re
from typing import Protocol


HANDOFF_PHRASES = (
    "转人工", "转客服", "人工服务", "人工客服", "真人客服", "联系人工",
    "找人工", "让人工", "找客服", "联系客服", "投诉", "账号被盗", "账户被盗",
    "盗号", "重复扣款", "二次扣款", "退款失败", "退款没到账",
)
GENERAL_CHAT_PHRASES = (
    "你好", "您好", "嗨", "哈喽", "hello", "早上好", "下午好", "晚上好",
    "谢谢", "感谢", "再见", "你是谁", "你叫什么", "在吗",
)
BUSINESS_TERMS = (
    "订单", "物流", "快递", "配送", "退款", "退货", "商品", "保修", "维修",
    "支付", "付款", "分期", "发票", "优惠券", "积分", "账号", "账户", "会员",
    "手机", "笔记本", "轻薄本", "耳机", "充电器", "数据线", "电池", "降噪",
    "扣款", "验证码", "密码", "登录", "个人信息", "运费", "换货", "价保", "到达", "送达", "几天到", "多久到",
)

SHIPMENT_TERMS = (
    "物流", "快递", "到哪", "配送", "到达", "送达", "送到", "几天到", "多久到", "什么时候到",
)

INTENT_ROUTES = {
    "general_chat": "general",
    "product_question": "service",
    "policy_question": "service",
    "order_query": "service",
    "shipment_query": "service",
    "refund_request": "aftersales",
    "return_request": "aftersales",
    "repair_request": "aftersales",
    "formal_appeal": "appeal",
    "risk_report": "risk",
    "human_handoff": "handoff",
}
ORDER_REQUIRED_INTENTS = {
    "order_query", "shipment_query", "refund_request", "return_request", "repair_request",
}
RISK_TERMS = ("账号被盗", "账户被盗", "盗号", "异地登录", "人身安全", "起火", "漏电", "爆炸")
APPEAL_TERMS = ("维权", "投诉", "维修两次", "维修两遍", "检测报告", "质量鉴定", "仍然坏", "拒绝退款")
REFUND_TERMS = ("退款", "退货", "退钱")
REFUND_POLICY_TERMS = ("政策", "要求", "条件", "规定", "时效", "多久", "哪些", "范围", "材料")
REFUND_NEGATION_TERMS = ("不想退款", "不是要退款", "不申请退款", "无需退款", "只想了解", "只是了解")
ORDER_PATTERN = re.compile(r"(?:XY\d{8}|SC\d{8,18})", re.IGNORECASE)
REPEATED_REPAIR_PATTERN = re.compile(
    r"(?:修|维修|返修).{0,8}(?:两|2|多|几)(?:次|回|遍).{0,12}(?:坏|故障|问题|没修好|未解决)"
)


@dataclass(frozen=True)
class IntentPrediction:
    intent: str
    confidence: float
    reason: str = ""
    route: str | None = None
    entities: dict[str, str] = field(default_factory=dict)
    candidate_intents: tuple[str, ...] = ()
    requires_clarification: bool = False
    clarification_question: str | None = None


@dataclass(frozen=True)
class RoutingDecision:
    route: str
    intent: str
    confidence: float
    source: str
    reason: str
    requires_order: bool = False
    entities: dict[str, str] = field(default_factory=dict)
    clarification_question: str | None = None


class IntentClassifier(Protocol):
    def classify_intent(self, message: str) -> IntentPrediction:
        ...


class SemanticRouter:
    """Three-tier router: deterministic rules, structured LLM, then controlled fallback."""

    def __init__(self, classifier: IntentClassifier | None = None, min_confidence: float = 0.65):
        self.classifier = classifier
        self.min_confidence = min_confidence

    def classify(self, message: str) -> RoutingDecision:
        normalized = message.strip()
        deterministic = self._deterministic_rule(normalized)
        if deterministic is not None:
            return deterministic

        if self.classifier is not None:
            try:
                prediction = self.classifier.classify_intent(normalized)
                if prediction.intent not in INTENT_ROUTES:
                    raise ValueError("intent is outside the allowed enum")
                expected_route = INTENT_ROUTES[prediction.intent]
                if prediction.route is not None and prediction.route != expected_route:
                    raise ValueError("route and intent are inconsistent")
                candidates = tuple(
                    item for item in prediction.candidate_intents
                    if item in INTENT_ROUTES and item != prediction.intent
                )
                if prediction.requires_clarification or candidates:
                    return RoutingDecision(
                        route="clarify",
                        intent=prediction.intent,
                        confidence=prediction.confidence,
                        source="llm_clarification",
                        reason=prediction.reason or "检测到多个无法确定优先级的业务意图",
                        entities=prediction.entities,
                        clarification_question=prediction.clarification_question or self._default_clarification(candidates),
                    )
                if prediction.confidence >= self.min_confidence:
                    return self._decision(
                        prediction.intent,
                        prediction.confidence,
                        "llm",
                        prediction.reason or "模型完成主意图语义分类",
                        entities=prediction.entities,
                    )
                if prediction.intent in {"risk_report", "formal_appeal"}:
                    return RoutingDecision(
                        route="handoff",
                        intent=prediction.intent,
                        confidence=prediction.confidence,
                        source="risk_guard",
                        reason="高风险意图置信度不足，转人工复核",
                        entities=prediction.entities,
                    )
                return RoutingDecision(
                    route="clarify",
                    intent=prediction.intent,
                    confidence=prediction.confidence,
                    source="low_confidence",
                    reason=prediction.reason or "模型置信度不足，需要用户补充信息",
                    entities=prediction.entities,
                    clarification_question=prediction.clarification_question or "请问你主要想咨询商品信息、查询订单，还是办理售后？",
                )
            except Exception:
                return self._rule_fallback(normalized, "模型输出不可用，已回退规则路由")
        return self._rule_fallback(normalized)

    @staticmethod
    def _decision(
        intent: str,
        confidence: float,
        source: str,
        reason: str,
        entities: dict[str, str] | None = None,
    ) -> RoutingDecision:
        return RoutingDecision(
            route=INTENT_ROUTES[intent],
            intent=intent,
            confidence=max(0.0, min(1.0, confidence)),
            source=source,
            reason=reason,
            requires_order=intent in ORDER_REQUIRED_INTENTS,
            entities=entities or {},
        )

    def _deterministic_rule(self, message: str) -> RoutingDecision | None:
        lower = message.lower()
        order_match = ORDER_PATTERN.search(message.upper())
        if any(term in lower for term in RISK_TERMS):
            return self._decision("risk_report", 1.0, "safety_rule", "命中账号或人身安全强制规则")
        if any(term in message for term in APPEAL_TERMS) or REPEATED_REPAIR_PATTERN.search(message):
            return self._decision("formal_appeal", 0.98, "safety_rule", "存在正式投诉或重复维修失败信号")
        if requires_human_handoff(message):
            return self._decision("human_handoff", 1.0, "deterministic_rule", "用户明确要求人工客服")
        if is_general_chat(message):
            return self._decision("general_chat", 0.98, "deterministic_rule", "明确的问候或礼貌用语")
        if any(term in message for term in REFUND_TERMS) and any(
            term in message for term in (*REFUND_POLICY_TERMS, *REFUND_NEGATION_TERMS)
        ):
            return self._decision("policy_question", 0.98, "deterministic_rule", "明确咨询退款政策，不执行退款")
        if order_match and any(term in message for term in SHIPMENT_TERMS):
            return self._decision("shipment_query", 0.99, "deterministic_rule", "订单号与物流查询表达完整")
        if order_match and any(term in message for term in REFUND_TERMS):
            return self._decision("refund_request", 0.97, "deterministic_rule", "订单号与退款办理表达完整")
        if order_match and any(term in message for term in ("订单", "订单状态", "支付", "付款", "查询")):
            return self._decision("order_query", 0.97, "deterministic_rule", "订单号与查询表达完整")
        return None

    def _rule_fallback(self, message: str, reason_prefix: str = "") -> RoutingDecision:
        def reason(value: str) -> str:
            return f"{reason_prefix}；{value}" if reason_prefix else value

        if is_general_chat(message):
            return self._decision("general_chat", 0.96, "rule_fallback", reason("匹配通用寒暄"))
        if any(term in message for term in SHIPMENT_TERMS):
            return self._decision("shipment_query", 0.9, "rule_fallback", reason("匹配物流查询表达"))
        if any(term in message for term in REFUND_TERMS):
            policy_only = any(term in message for term in (*REFUND_POLICY_TERMS, *REFUND_NEGATION_TERMS))
            if policy_only:
                return self._decision("policy_question", 0.92, "rule_fallback", reason("退款政策咨询，不执行退款"))
            return self._decision("refund_request", 0.86, "rule_fallback", reason("匹配退款办理诉求"))
        if any(term in message for term in ("订单", "订单状态", "支付", "付款")):
            return self._decision("order_query", 0.88, "rule_fallback", reason("匹配订单查询表达"))
        return self._decision("product_question", 0.7, "rule_fallback", reason("按低风险商品知识咨询降级"))

    @staticmethod
    def _default_clarification(candidates: tuple[str, ...]) -> str:
        if candidates:
            return "你的问题同时涉及多个事项。请问你希望优先处理哪一项？"
        return "为了准确处理，请补充说明你最希望客服解决的问题。"


def requires_human_handoff(message: str) -> bool:
    return any(phrase in message for phrase in HANDOFF_PHRASES)


def is_general_chat(message: str) -> bool:
    normalized = message.strip().lower()
    return any(phrase in normalized for phrase in GENERAL_CHAT_PHRASES) and not any(
        term in normalized for term in BUSINESS_TERMS
    )
