import time
from collections.abc import Callable
from typing import TypeVar

from app.commerce_repository import CommerceError, CommerceRepository
from app.observability import observe_tool


class BusinessRuleError(Exception):
    pass


_repository: CommerceRepository | None = None
T = TypeVar("T")


def configure_business_tools(repository: CommerceRepository) -> None:
    global _repository
    _repository = repository


def _repo() -> CommerceRepository:
    if _repository is None:
        raise BusinessRuleError("订单服务尚未初始化")
    return _repository


def _run_tool(name: str, operation: Callable[[], T]) -> T:
    started = time.perf_counter()
    status = "success"
    try:
        return operation()
    except CommerceError as exc:
        status = "blocked"
        raise BusinessRuleError(str(exc)) from exc
    except Exception:
        status = "error"
        raise
    finally:
        observe_tool(name, status, time.perf_counter() - started)


def get_order(order_id: str, user_id: str) -> dict:
    return _run_tool("get_order", lambda: _repo().tool_order(order_id, user_id))


def get_shipment(order_id: str, user_id: str) -> dict:
    return _run_tool("get_shipment", lambda: _repo().tool_shipment(order_id, user_id))


def evaluate_refund(order_id: str, user_id: str) -> dict:
    return _run_tool("evaluate_refund", lambda: _repo().evaluate_refund(order_id, user_id))


def create_refund(order_id: str, user_id: str) -> dict:
    return _run_tool("create_refund", lambda: _repo().create_refund(order_id, user_id))
