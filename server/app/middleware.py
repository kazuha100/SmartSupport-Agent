import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int, chat_requests_per_minute: int, redis_url: str = ""):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.chat_requests_per_minute = chat_requests_per_minute
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()
        self.redis = None
        if redis_url:
            from redis.asyncio import from_url

            self.redis = from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS" or request.url.path.startswith("/health"):
            return await call_next(request)
        host = request.client.host if request.client else "unknown"
        bucket = "chat" if request.url.path.startswith("/api/chat") else "api"
        key = f"{host}:{bucket}"
        limit = self.chat_requests_per_minute if bucket == "chat" else self.requests_per_minute
        if self.redis is not None:
            try:
                window = int(time.time() // 60)
                redis_key = f"smart-support:rate:{key}:{window}"
                count = await self.redis.incr(redis_key)
                if count == 1:
                    await self.redis.expire(redis_key, 61)
                if count > limit:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "请求过于频繁，请稍后重试"},
                        headers={"Retry-After": "60"},
                    )
                return await call_next(request)
            except Exception:
                pass
        now = time.monotonic()
        with self.lock:
            queue = self.requests[key]
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if len(queue) >= limit:
                retry_after = max(1, int(60 - (now - queue[0])))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后重试"},
                    headers={"Retry-After": str(retry_after)},
                )
            queue.append(now)
        return await call_next(request)
