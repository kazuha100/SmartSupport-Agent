from uuid import uuid4
import json

from fastapi.testclient import TestClient

from app.main import app, database, support_graph  # noqa: E402


client = TestClient(app)


def auth_headers(username: str = "admin", password: str = "Admin123!") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def register_customer() -> tuple[dict[str, str], dict]:
    username = f"customer_{uuid4().hex[:8]}"
    response = client.post("/api/auth/register", json={
        "username": username, "display_name": "林晓雨", "password": "Linxy2026!",
    })
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, response.json()["user"]


def create_paid_order(headers: dict[str, str], product_id: str = "P-C65") -> str:
    address = client.post("/api/shop/addresses", headers=headers, json={
        "recipient": "林晓雨", "phone": "13800138000", "province": "上海市",
        "city": "上海市", "detail": "浦东新区世纪大道 100 号", "is_default": True,
    })
    assert address.status_code == 200
    assert client.post("/api/shop/cart/items", headers=headers, json={"product_id": product_id, "quantity": 1}).status_code == 200
    order = client.post("/api/shop/orders", headers=headers, json={"address_id": address.json()["address_id"]})
    assert order.status_code == 200
    paid = client.post(f"/api/shop/orders/{order.json()['order_id']}/pay", headers=headers, json={"success": True})
    assert paid.status_code == 200
    return paid.json()["order_id"]


ADMIN_HEADERS = auth_headers()
CUSTOMER_HEADERS, CUSTOMER_USER = register_customer()


def test_chat_accepts_utf8_chinese() -> None:
    order_id = create_paid_order(CUSTOMER_HEADERS)
    response = client.post(
        "/api/chat",
        json={
            "session_id": "utf8-test",
            "message": f"订单 {order_id} 到哪里了？",
        },
        headers=CUSTOMER_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "shipment_query"
    assert payload["tool_calls"][0]["name"] == "get_shipment"
    assert "商家正在备货" in payload["answer"]
    assert "上海嘉定仓" in payload["answer"]
    assert "预计还需要" in payload["answer"]
    assert payload["citations"][0]["doc_id"] == "logistics_001"


def test_employee_can_list_shop_conversations() -> None:
    session_id = f"shop-test-{uuid4().hex}"
    sent = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "商城里的消息需要出现在客服后台"},
        headers=CUSTOMER_HEADERS,
    )
    assert sent.status_code == 200

    listed = client.get("/api/conversations", params={"prefix": "shop-test-"}, headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    summary = next(item for item in listed.json() if item["session_id"] == session_id)
    assert summary["user_id"] == CUSTOMER_USER["user_id"]
    assert summary["display_name"] == "林晓雨"
    assert summary["last_user_message"] == "商城里的消息需要出现在客服后台"
    assert summary["last_assistant_message"]

    own = client.get("/api/conversations", headers=CUSTOMER_HEADERS)
    assert own.status_code == 200
    assert all(item["user_id"] == CUSTOMER_USER["user_id"] for item in own.json())


def test_customer_can_share_product_card_idempotently() -> None:
    session_id = f"product-share-{uuid4().hex}"
    payload = {"session_id": session_id, "product_id": "P-C3"}

    first = client.post("/api/chat/product-share", json=payload, headers=CUSTOMER_HEADERS)
    repeated = client.post("/api/chat/product-share", json=payload, headers=CUSTOMER_HEADERS)

    assert first.status_code == 201
    assert first.json()["created"] is True
    assert repeated.status_code == 201
    assert repeated.json()["created"] is False
    messages = client.get(f"/api/conversations/{session_id}/messages", headers=CUSTOMER_HEADERS).json()
    assert len(messages) == 1
    assert messages[0]["attachment"]["type"] == "product"
    assert messages[0]["attachment"]["product"]["product_id"] == "P-C3"
    assert messages[0]["attachment"]["product"]["name"]

    conversations = client.get("/api/conversations", headers=CUSTOMER_HEADERS).json()
    conversation = next(item for item in conversations if item["session_id"] == session_id)
    assert conversation["product_id"] == "P-C3"


def test_api_remembers_order_within_session() -> None:
    order_id = create_paid_order(CUSTOMER_HEADERS)
    session_id = f"memory-api-{uuid4().hex}"
    first = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": f"查询订单 {order_id}",
        },
        headers=CUSTOMER_HEADERS,
    )
    assert first.status_code == 200

    follow_up = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": "它到哪里了？",
        },
        headers=CUSTOMER_HEADERS,
    )
    payload = follow_up.json()
    assert payload["intent"] == "shipment_query"
    assert payload["tool_calls"][0]["arguments"]["order_id"] == order_id
    assert any(step["name"] == "会话记忆" for step in payload["trace"])

    state = client.get(
        f"/api/conversations/{session_id}/state",
        headers=CUSTOMER_HEADERS,
    )
    assert state.json()["turn_count"] == 2
    assert state.json()["last_order_id"] == order_id

    history = client.get(f"/api/conversations/{session_id}/messages", headers=CUSTOMER_HEADERS)
    assert history.status_code == 200
    assert [item["role"] for item in history.json()] == ["user", "assistant", "user", "assistant"]
    assert history.json()[-1]["result"]["intent"] == "shipment_query"


def test_document_management_api() -> None:
    uploaded = client.post(
        "/api/admin/documents",
        files={"file": ("interview-policy.md", "# 面试专享政策\n\n测试用户可享受专属服务。", "text/markdown")},
        data={"title": "面试专享政策", "version": "1.0", "visibility": "internal"},
        headers=ADMIN_HEADERS,
    )
    assert uploaded.status_code == 201
    doc_id = uploaded.json()["doc_id"]

    detail = client.get(f"/api/admin/documents/{doc_id}", headers=ADMIN_HEADERS)
    assert detail.status_code == 200
    assert detail.json()["chunks"]
    assert detail.json()["content"].startswith("# 面试专享政策")

    disabled = client.patch(
        f"/api/admin/documents/{doc_id}/status",
        json={"status": "disabled"},
        headers=ADMIN_HEADERS,
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"

    deleted = client.delete(f"/api/admin/documents/{doc_id}", headers=ADMIN_HEADERS)
    assert deleted.status_code == 200


def test_authentication_and_rbac() -> None:
    assert client.post("/api/chat", json={"session_id": "no-auth", "message": "你好"}).status_code == 401
    assert client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong-password"}
    ).status_code == 401

    assert client.post(
        "/api/auth/login", json={"username": "agent", "password": "Agent123!"}
    ).status_code == 401
    forbidden = client.get("/api/admin/documents", headers=CUSTOMER_HEADERS)
    assert forbidden.status_code == 403

    me = client.get("/api/auth/me", headers=ADMIN_HEADERS)
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    assert me.json()["display_name"] == "客服管理员"


def test_human_handoff_ticket_lifecycle() -> None:
    session_id = f"ticket-api-{uuid4().hex}"
    handoff = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "我要人工客服"},
        headers=CUSTOMER_HEADERS,
    )
    assert handoff.status_code == 200
    ticket_id = handoff.json()["ticket_id"]
    assert ticket_id.startswith("TK")

    agent_headers = ADMIN_HEADERS
    accepted = client.post(f"/api/tickets/{ticket_id}/accept", headers=agent_headers)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "assigned"

    replied = client.post(
        f"/api/tickets/{ticket_id}/replies",
        json={"content": "您好，人工客服已接管。"},
        headers=agent_headers,
    )
    assert replied.status_code == 200
    assert replied.json()["reply_count"] == 1

    resolved = client.post(f"/api/tickets/{ticket_id}/resolve", headers=agent_headers)
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    assert client.get(f"/api/tickets/{ticket_id}", headers=CUSTOMER_HEADERS).status_code == 200


def test_streaming_tool_response() -> None:
    order_id = create_paid_order(CUSTOMER_HEADERS)
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": f"stream-{uuid4().hex}", "message": f"查询订单 {order_id}"},
        headers=CUSTOMER_HEADERS,
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert any(event["type"] == "delta" for event in events)
    assert any(event["type"] == "status" for event in events)
    done = next(event for event in events if event["type"] == "done")
    assert done["data"]["intent"] == "order_query"


def test_streaming_greeting_does_not_create_ticket() -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": f"greeting-{uuid4().hex}", "message": "你好啊"},
        headers=ADMIN_HEADERS,
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    done = next(event for event in events if event["type"] == "done")
    assert done["data"]["intent"] == "general_chat"
    assert done["data"]["needs_human"] is False
    assert done["data"]["ticket_id"] is None


def test_repeated_off_topic_questions_skip_agent_after_limit(monkeypatch) -> None:
    session_id = f"off-topic-{uuid4().hex}"
    calls = 0
    original_respond = support_graph.respond

    def counted_respond(message: str, user_id: str, current_session_id: str):
        nonlocal calls
        calls += 1
        return original_respond(message, user_id, current_session_id)

    monkeypatch.setattr(support_graph, "respond", counted_respond)
    questions = ("讲个笑话", "帮我写一首诗", "解释一下量子力学", "帮我写排序代码")
    responses = [
        client.post(
            "/api/chat",
            json={"session_id": session_id, "message": question},
            headers=CUSTOMER_HEADERS,
        )
        for question in questions
    ]

    assert all(response.status_code == 200 for response in responses)
    assert calls == 3
    assert responses[-1].json()["intent"] == "off_topic_limited"
    assert "未调用大模型" in responses[-1].json()["trace"][0]["detail"]

    business = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "P-C3 支持防水吗？"},
        headers=CUSTOMER_HEADERS,
    )
    assert business.status_code == 200
    assert business.json()["intent"] != "off_topic_limited"
    assert calls == 4


def test_health_and_audit_endpoints() -> None:
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"
    assert ready.headers["X-Content-Type-Options"] == "nosniff"

    audit = client.get("/api/admin/audit-logs?limit=10", headers=ADMIN_HEADERS)
    assert audit.status_code == 200
    assert isinstance(audit.json(), list)

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "smart_support_http_requests_total" in metrics.text


def test_dashboard_uses_real_questions_and_reports_knowledge_gaps() -> None:
    frequent_question = "七天无理由退货有什么要求？"
    gap_question = "量子纠缠课程怎么报名？"
    for index, question in enumerate((frequent_question, frequent_question, gap_question)):
        response = client.post(
            "/api/chat",
            json={"session_id": f"analytics-{index}-{uuid4().hex}", "message": question},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200

    dashboard = client.get("/api/dashboard/metrics", headers=ADMIN_HEADERS)
    assert dashboard.status_code == 200
    analytics = dashboard.json()["question_analytics"]
    assert analytics["total_questions"] >= 3
    assert any(item["question"] == frequent_question and item["count"] >= 2 for item in analytics["top_questions"])
    gap = next(item for item in analytics["uncovered_questions"] if item["question"] == gap_question)
    assert gap["occurrences"]
    assert gap["occurrences"][0]["session_id"].startswith("analytics-")
    assert gap["occurrences"][0]["display_name"]


def test_admin_knowledge_search() -> None:
    response = client.post(
        "/api/admin/knowledge/search",
        json={"query": "七天无理由有什么要求", "limit": 3},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["count"] > 0
    assert response.json()["results"][0]["title"] == "七天无理由退货政策"


def test_single_staff_account_can_complete_appeal_workflow() -> None:
    customer_headers, _ = register_customer()
    agent_headers = ADMIN_HEADERS
    order_id = create_paid_order(customer_headers, "P-C65")
    session_id = f"shop-{order_id}"
    created = client.post(f"/api/orders/{order_id}/appeals", headers=customer_headers, json={
        "session_id": session_id, "appeal_type": "rights_protection",
        "description": "充电器使用时持续异常发热，我要求正式调查并提供售后处理方案。",
    })
    assert created.status_code == 200
    appeal_id = created.json()["appeal"]["appeal_id"]
    assert created.json()["appeal"]["status"] == "submitted"
    assert created.json()["appeal"]["execution"] is None

    accepted = client.post(f"/api/appeals/{appeal_id}/accept", headers=agent_headers)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "investigating"

    # Startup migrations must not move an actively assigned case back to submitted.
    database._migrate_columns()
    assert client.get(f"/api/appeals/{appeal_id}", headers=agent_headers).json()["status"] == "investigating"

    requested = client.post(f"/api/appeals/{appeal_id}/material-requests", headers=agent_headers, json={
        "content": "请上传产品异常发热照片", "due_at": None,
    })
    assert requested.status_code == 200
    assert requested.json()["status"] == "waiting_customer"
    uploaded = client.post(
        f"/api/appeals/{appeal_id}/attachments", headers=customer_headers,
        files={"file": ("evidence.png", b"valid-image-content", "image/png")},
    )
    assert uploaded.status_code == 201
    attachment_id = uploaded.json()["attachment_id"]
    detail = client.get(f"/api/appeals/{appeal_id}", headers=customer_headers).json()
    assert detail["status"] == "investigating"
    assert detail["material_requests"][0]["status"] == "submitted"
    messages = client.get(f"/api/conversations/{session_id}/messages", headers=customer_headers).json()
    assert any("已补充材料" in message["content"] for message in messages)

    reviewed = client.post(
        f"/api/appeals/{appeal_id}/attachments/{attachment_id}/review", headers=agent_headers,
        json={"status": "accepted", "note": "照片内容清晰，可以支持异常发热诉求。"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["material_requests"][0]["status"] == "completed"

    investigation = client.post(f"/api/appeals/{appeal_id}/investigation", headers=agent_headers, json={
        "responsibility": "merchant", "conclusion": "订单与用户证据有效，商品异常发热应由商家承担售后责任。",
    })
    assert investigation.status_code == 200
    proposed = client.post(f"/api/appeals/{appeal_id}/proposal", headers=agent_headers, json={
        "action": "refund", "amount_cents": 19900, "reason": "依据质量问题售后政策，为用户办理全额退款。",
    })
    assert proposed.status_code == 200
    submitted = client.post(f"/api/appeals/{appeal_id}/submit-approval", headers=agent_headers)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_approval"
    assert submitted.json()["execution"] is None

    assert client.post(f"/api/appeals/{appeal_id}/approval", headers=customer_headers, json={"decision": "approve", "comment": "同意"}).status_code == 403
    approved = client.post(f"/api/appeals/{appeal_id}/approval", headers=ADMIN_HEADERS, json={
        "decision": "approve", "comment": "证据和政策依据完整，同意沙箱退款。",
    })
    assert approved.status_code == 200
    assert approved.json()["status"] == "waiting_confirmation"
    assert approved.json()["execution"]["status"] == "completed"
    reference = approved.json()["execution"]["sandbox_reference"]
    duplicate = client.post(f"/api/appeals/{appeal_id}/approval", headers=ADMIN_HEADERS, json={"decision": "approve", "comment": "重复审批"})
    assert duplicate.status_code == 409
    assert client.get(f"/api/appeals/{appeal_id}", headers=ADMIN_HEADERS).json()["execution"]["sandbox_reference"] == reference

    objected = client.post(f"/api/appeals/{appeal_id}/object", headers=customer_headers, json={"comment": "退款之外还需要检测故障原因"})
    assert objected.status_code == 200
    assert objected.json()["status"] == "investigating"
    assert any(event["detail"].get("reference") == reference for event in objected.json()["events"] if event["event_type"] == "execution_completed")
    assert client.post(f"/api/appeals/{appeal_id}/investigation", headers=agent_headers, json={
        "responsibility": "merchant", "conclusion": "复核用户异议后确认需要增加维修检测流程并保留原退款记录。",
    }).status_code == 200
    assert client.post(f"/api/appeals/{appeal_id}/proposal", headers=agent_headers, json={
        "action": "repair", "amount_cents": None, "reason": "安排沙箱维修检测业务单并向用户反馈检测结论。",
    }).status_code == 200
    assert client.post(f"/api/appeals/{appeal_id}/submit-approval", headers=agent_headers).status_code == 200
    revised = client.post(f"/api/appeals/{appeal_id}/approval", headers=ADMIN_HEADERS, json={
        "decision": "approve", "comment": "同意增加维修检测流程。",
    })
    assert revised.status_code == 200
    assert revised.json()["status"] == "waiting_confirmation"
    assert revised.json()["execution"]["sandbox_reference"] != reference
    assert len(revised.json()["executions"]) == 2
    assert revised.json()["executions"][0]["sandbox_reference"] == reference

    confirmed = client.post(f"/api/appeals/{appeal_id}/confirm", headers=customer_headers, json={"comment": "处理结果已确认"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "resolved"
    assert any(event["event_type"] == "customer_confirmed" for event in confirmed.json()["events"])


def test_appeal_rejection_return_and_permission_boundaries() -> None:
    customer_headers, customer = register_customer()
    other_customer_headers, _ = register_customer()
    agent_headers = ADMIN_HEADERS
    order_id = create_paid_order(customer_headers, "P-C65")
    session_id = f"shop-{order_id}"
    created = client.post(f"/api/orders/{order_id}/appeals", headers=customer_headers, json={
        "session_id": session_id, "appeal_type": "repair",
        "description": "充电器间歇性断电，需要核验证据并安排维修处理。",
    })
    appeal_id = created.json()["appeal"]["appeal_id"]

    assert client.get(f"/api/appeals/{appeal_id}", headers=other_customer_headers).status_code == 404
    assert client.post(
        f"/api/appeals/{appeal_id}/proposal", headers=agent_headers,
        json={"action": "repair", "amount_cents": None, "reason": "尚未受理时不能提交处理方案。"},
    ).status_code == 409

    assert client.post(f"/api/appeals/{appeal_id}/accept", headers=agent_headers).status_code == 200
    requested = client.post(
        f"/api/appeals/{appeal_id}/material-requests", headers=agent_headers,
        json={"content": "请上传能够看清故障现象的照片", "due_at": None},
    ).json()
    request_id = requested["material_requests"][0]["request_id"]
    uploaded = client.post(
        f"/api/appeals/{appeal_id}/attachments", headers=customer_headers,
        data={"material_request_id": request_id},
        files={"file": ("blurred.png", b"blurred-image-content", "image/png")},
    )
    rejected = client.post(
        f"/api/appeals/{appeal_id}/attachments/{uploaded.json()['attachment_id']}/review",
        headers=agent_headers,
        json={"status": "rejected", "note": "图片模糊，无法识别故障位置。"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "waiting_customer"
    assert rejected.json()["material_requests"][0]["status"] == "pending"
    customer_events = client.get(f"/api/appeals/{appeal_id}", headers=customer_headers).json()["events"]
    assert any(event["event_type"] == "attachment_reviewed" for event in customer_events)

    uploaded_again = client.post(
        f"/api/appeals/{appeal_id}/attachments", headers=customer_headers,
        data={"material_request_id": request_id},
        files={"file": ("clear.png", b"clear-image-content", "image/png")},
    )
    assert client.post(
        f"/api/appeals/{appeal_id}/attachments/{uploaded_again.json()['attachment_id']}/review",
        headers=agent_headers,
        json={"status": "accepted", "note": "照片清晰有效。"},
    ).json()["material_requests"][0]["status"] == "completed"

    assert client.post(f"/api/appeals/{appeal_id}/investigation", headers=agent_headers, json={
        "responsibility": "merchant", "conclusion": "订单有效，清晰照片能够证明商品存在间歇性断电故障。",
    }).status_code == 200
    excessive = client.post(f"/api/appeals/{appeal_id}/proposal", headers=agent_headers, json={
        "action": "refund", "amount_cents": 999999, "reason": "尝试提交超过订单实付金额的退款方案。",
    })
    assert excessive.status_code == 409

    assert client.post(f"/api/appeals/{appeal_id}/proposal", headers=agent_headers, json={
        "action": "repair", "amount_cents": None, "reason": "先安排沙箱维修检测并向用户反馈检测结果。",
    }).status_code == 200
    assert client.post(f"/api/appeals/{appeal_id}/submit-approval", headers=agent_headers).status_code == 200
    returned = client.post(f"/api/appeals/{appeal_id}/approval", headers=ADMIN_HEADERS, json={
        "decision": "return", "comment": "请补充维修时限和结果通知方式。",
    })
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"
    assert returned.json()["execution"] is None
    assert any(event["event_type"] == "approval_returned" for event in returned.json()["events"])
    assert returned.json()["user_id"] == customer["user_id"]
