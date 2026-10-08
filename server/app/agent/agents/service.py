from .base import BusinessAgent


class ServiceAgent(BusinessAgent):
    """Handles low-risk knowledge, product, order, and shipment requests."""

    key = "service"
    label = "Service Agent"
