from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Literal

from app.routing import BUSINESS_TERMS, GENERAL_CHAT_PHRASES, requires_human_handoff


MessageCategory = Literal["business", "neutral", "off_topic"]

ORDER_OR_PRODUCT_PATTERN = re.compile(r"(?:XY\d{8}|SC\d{8,18}|P-[A-Z0-9]+)", re.IGNORECASE)
SUPPORT_TERMS = (
    "客服", "商城", "购买", "下单", "收货", "地址", "价格", "库存", "缺货", "到货",
    "规格", "参数", "型号", "颜色", "尺寸", "重量", "材质", "兼容", "防水", "续航",
    "质量", "故障", "损坏", "坏了", "不能用", "怎么用", "使用方法", "安装", "激活",
    "售后", "退换", "换货", "申诉", "维权", "赔偿", "补偿", "发货", "签收", "包裹",
    "取消", "修改订单", "收货人", "开票", "电子票", "余额", "权益", "活动", "折扣",
)


def classify_message(message: str) -> MessageCategory:
    """Classify with conservative deterministic rules so the guard never spends an LLM call."""
    normalized = message.strip().lower()
    if not normalized:
        return "neutral"
    if requires_human_handoff(normalized):
        return "business"
    if ORDER_OR_PRODUCT_PATTERN.search(normalized):
        return "business"
    if any(term in normalized for term in (*BUSINESS_TERMS, *SUPPORT_TERMS)):
        return "business"
    if any(phrase in normalized for phrase in GENERAL_CHAT_PHRASES):
        return "neutral"
    return "off_topic"


@dataclass(frozen=True)
class OffTopicDecision:
    category: MessageCategory
    count: int = 0
    blocked: bool = False


class OffTopicGuard:
    """Track consecutive off-topic questions per user conversation."""

    def __init__(self, max_allowed: int, window_seconds: int, redis_url: str = ""):
        self.max_allowed = max(0, max_allowed)
        self.window_seconds = max(1, window_seconds)
        self.redis = None
        if redis_url:
            from redis import Redis

            self.redis = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        self._fallback: dict[str, tuple[int, float]] = {}
        self._lock = Lock()

    def check(self, user_id: str, session_id: str, message: str) -> OffTopicDecision:
        category = classify_message(message)
        key = self._key(user_id, session_id)
        if category == "business":
            self._reset(key)
            return OffTopicDecision(category=category)
        if category == "neutral":
            return OffTopicDecision(category=category)

        count = self._increment(key)
        return OffTopicDecision(
            category=category,
            count=count,
            blocked=count > self.max_allowed,
        )

    @staticmethod
    def _key(user_id: str, session_id: str) -> str:
        identity = hashlib.sha256(f"{user_id}\0{session_id}".encode("utf-8")).hexdigest()
        return f"smart-support:off-topic:{identity}"

    def _reset(self, key: str) -> None:
        if self.redis is not None:
            try:
                self.redis.delete(key)
                return
            except Exception:
                pass
        with self._lock:
            self._fallback.pop(key, None)

    def _increment(self, key: str) -> int:
        if self.redis is not None:
            try:
                pipeline = self.redis.pipeline(transaction=True)
                pipeline.incr(key)
                pipeline.expire(key, self.window_seconds)
                count, _ = pipeline.execute()
                return int(count)
            except Exception:
                pass

        now = time.monotonic()
        with self._lock:
            count, expires_at = self._fallback.get(key, (0, 0.0))
            if expires_at <= now:
                count = 0
            count += 1
            self._fallback[key] = (count, now + self.window_seconds)
            return count
