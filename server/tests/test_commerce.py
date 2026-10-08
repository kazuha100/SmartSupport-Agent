from app.commerce_repository import CommerceRepository
from app.database import Database


def make_repository(database: Database) -> CommerceRepository:
    repository = CommerceRepository(database)
    repository.seed()
    return repository


def add_address(repository: CommerceRepository, user_id: str = "test-customer") -> str:
    return repository.create_address(user_id, {
        "recipient": "林晓雨", "phone": "13800138000", "province": "上海市",
        "city": "上海市", "detail": "浦东新区世纪大道 100 号", "is_default": True,
    })["address_id"]


def test_seeded_catalog_and_cart(postgres_database: Database) -> None:
    repository = make_repository(postgres_database)

    assert len(repository.list_products()) == 8
    cart = repository.put_cart_item("test-customer", "P-C3", 2)
    assert cart["items"][0]["name"] == "星云降噪耳机 C3"
    assert cart["total_cents"] == 119800


def test_checkout_payment_and_inventory_are_persisted(postgres_database: Database) -> None:
    repository = make_repository(postgres_database)
    before = repository.get_product("P-C65")["stock"]
    address_id = add_address(repository)
    repository.put_cart_item("test-customer", "P-C65", 2)

    order = repository.create_order("test-customer", address_id)
    assert order["status"] == "pending_payment"
    assert order["payment_status"] == "pending"
    assert repository.cart("test-customer")["items"] == []

    paid = repository.pay_order(order["order_id"], "test-customer", True)
    assert paid["status"] == "paid"
    assert paid["shipment"]["latest_event"] == "商家正在备货"
    assert repository.get_product("P-C65")["stock"] == before - 2


def test_order_ownership_and_appeal_link(postgres_database: Database) -> None:
    repository = make_repository(postgres_database)
    address_id = add_address(repository)
    repository.put_cart_item("test-customer", "P-S8", 1)
    order = repository.create_order("test-customer", address_id)

    assert repository.get_order(order["order_id"], "other-user") is None
    appeal = repository.create_appeal(order["order_id"], "test-customer", {
        "session_id": "appeal-test",
        "appeal_type": "rights_protection",
        "description": "手机出现严重质量问题，我要求提交正式售后维权处理。",
    })
    attached = repository.attach_appeal_result(appeal["appeal_id"], "TK-TEST", {"route": "appeal"})
    assert attached["order_id"] == order["order_id"]
    assert attached["ticket_id"] == "TK-TEST"
    assert attached["status"] == "submitted"
    assert attached["events"][0]["event_type"] == "submitted"
