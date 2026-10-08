from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.database import (
    AddressRecord,
    AppealAttachmentRecord,
    AppealEventRecord,
    AppealExecutionRecord,
    AppealMaterialRequestRecord,
    AppealRecord,
    CartItemRecord,
    CommerceOrderItemRecord,
    CommerceOrderRecord,
    Database,
    PaymentRecord,
    ProductRecord,
    RefundRecord,
    ShipmentRecord,
)


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


PRODUCTS = (
    ("P-C3", "星云降噪耳机 C3", "影音设备", "自适应主动降噪，40 小时续航，支持双设备连接。", 59900, 86, "/assets/products/headphones.jpg", {"降噪": "自适应 ANC", "续航": "40 小时", "连接": "蓝牙 5.4"}, 12),
    ("P-S8", "星云手机 S8", "手机数码", "轻薄旗舰手机，专业影像系统与全天候续航。", 399900, 42, "/assets/products/phone.jpg", {"屏幕": "6.7 英寸 OLED", "存储": "256GB", "防护": "IP68"}, 12),
    ("P-B2", "星云轻薄本 B2", "电脑办公", "14 英寸高性能轻薄本，适合移动办公与内容创作。", 659900, 25, "/assets/products/laptop.jpg", {"处理器": "8 核", "内存": "16GB", "硬盘": "1TB SSD"}, 24),
    ("P-C65", "65W GaN 快充套装", "数码配件", "双 USB-C 接口氮化镓充电器，兼容手机、平板和笔记本。", 19900, 150, "/assets/products/charger.jpg", {"功率": "65W", "接口": "2C1A", "协议": "PD/PPS"}, 12),
    ("P-AIR", "云境智能空气净化器", "智能家电", "甲醛与颗粒物双传感，支持 App 远程控制。", 239900, 34, "/assets/products/air-purifier.jpg", {"CADR": "620m3/h", "噪声": "32dB", "适用面积": "45-72m2"}, 24),
    ("P-VAC", "极光扫拖机器人 V6", "智能家电", "自动集尘与热水洗拖布，全屋路径规划。", 329900, 31, "/assets/products/robot-vacuum.jpg", {"吸力": "8000Pa", "避障": "双线激光", "基站": "自动集尘"}, 24),
    ("P-DIS", "智净洗碗机 D8", "厨卫家电", "嵌入式 16 套容量，分层洗与高温除菌。", 469900, 18, "/assets/products/dishwasher.jpg", {"容量": "16 套", "能效": "一级", "烘干": "热风"}, 36),
    ("P-TV", "视界 MiniLED 电视 M7", "影音家电", "65 英寸 MiniLED 高刷电视，支持影院级音画。", 529900, 20, "/assets/products/tv.jpg", {"尺寸": "65 英寸", "刷新率": "144Hz", "分区": "1024"}, 24),
)


class CommerceError(ValueError):
    pass


class CommerceRepository:
    def __init__(self, database: Database):
        self.database = database

    def seed(self) -> None:
        with self.database.session_factory() as session:
            for values in PRODUCTS:
                if session.get(ProductRecord, values[0]) is None:
                    session.add(ProductRecord(
                        product_id=values[0], name=values[1], category=values[2], description=values[3],
                        price_cents=values[4], stock=values[5], image_url=values[6],
                        specs_json=json.dumps(values[7], ensure_ascii=False), warranty_months=values[8],
                    ))
            session.commit()

    def list_products(self, category: str | None = None) -> list[dict]:
        with self.database.session_factory() as session:
            query = select(ProductRecord).where(ProductRecord.active == 1)
            if category:
                query = query.where(ProductRecord.category == category)
            return [self._product(item) for item in session.scalars(query.order_by(ProductRecord.product_id)).all()]

    def get_product(self, product_id: str) -> dict | None:
        with self.database.session_factory() as session:
            item = session.get(ProductRecord, product_id)
            return self._product(item) if item and item.active else None

    def cart(self, user_id: str) -> dict:
        with self.database.session_factory() as session:
            rows = session.execute(
                select(CartItemRecord, ProductRecord)
                .join(ProductRecord, CartItemRecord.product_id == ProductRecord.product_id)
                .where(CartItemRecord.user_id == user_id)
                .order_by(CartItemRecord.id)
            ).all()
            items = [{**self._product(product), "quantity": cart.quantity, "cart_item_id": cart.id} for cart, product in rows]
            return {"items": items, "total_cents": sum(item["price_cents"] * item["quantity"] for item in items)}

    def put_cart_item(self, user_id: str, product_id: str, quantity: int) -> dict:
        with self.database.session_factory() as session:
            product = session.get(ProductRecord, product_id)
            if not product or not product.active:
                raise CommerceError("商品不存在或已下架")
            if quantity > product.stock:
                raise CommerceError("库存不足")
            row = session.scalar(select(CartItemRecord).where(CartItemRecord.user_id == user_id, CartItemRecord.product_id == product_id))
            if row:
                row.quantity = min(product.stock, row.quantity + quantity)
            else:
                session.add(CartItemRecord(user_id=user_id, product_id=product_id, quantity=quantity))
            session.commit()
        return self.cart(user_id)

    def update_cart_item(self, user_id: str, item_id: int, quantity: int) -> dict:
        with self.database.session_factory() as session:
            row = session.get(CartItemRecord, item_id)
            if not row or row.user_id != user_id:
                raise CommerceError("购物车商品不存在")
            product = session.get(ProductRecord, row.product_id)
            if quantity > product.stock:
                raise CommerceError("库存不足")
            if quantity == 0:
                session.delete(row)
            else:
                row.quantity = quantity
            session.commit()
        return self.cart(user_id)

    def list_addresses(self, user_id: str) -> list[dict]:
        with self.database.session_factory() as session:
            return [self._address(item) for item in session.scalars(select(AddressRecord).where(AddressRecord.user_id == user_id).order_by(AddressRecord.is_default.desc())).all()]

    def create_address(self, user_id: str, payload: dict) -> dict:
        with self.database.session_factory() as session:
            if payload.get("is_default"):
                for item in session.scalars(select(AddressRecord).where(AddressRecord.user_id == user_id)).all():
                    item.is_default = 0
            record = AddressRecord(address_id=f"ADDR-{uuid4().hex[:10].upper()}", user_id=user_id, **{**payload, "is_default": int(payload.get("is_default", False))})
            session.add(record)
            session.commit()
            return self._address(record)

    def update_address(self, user_id: str, address_id: str, payload: dict) -> dict:
        with self.database.session_factory() as session:
            record = session.get(AddressRecord, address_id)
            if not record or record.user_id != user_id:
                raise CommerceError("收货地址不存在")
            if payload.get("is_default"):
                for item in session.scalars(select(AddressRecord).where(AddressRecord.user_id == user_id)).all():
                    item.is_default = 0
            for key, value in payload.items():
                setattr(record, key, int(value) if key == "is_default" else value)
            session.commit()
            return self._address(record)

    def delete_address(self, user_id: str, address_id: str) -> None:
        with self.database.session_factory() as session:
            record = session.get(AddressRecord, address_id)
            if not record or record.user_id != user_id:
                raise CommerceError("收货地址不存在")
            session.delete(record); session.commit()

    def create_order(self, user_id: str, address_id: str) -> dict:
        with self.database.session_factory() as session:
            address = session.get(AddressRecord, address_id)
            if not address or address.user_id != user_id:
                raise CommerceError("收货地址不存在")
            rows = session.execute(select(CartItemRecord, ProductRecord).join(ProductRecord).where(CartItemRecord.user_id == user_id)).all()
            if not rows:
                raise CommerceError("购物车为空")
            for cart, product in rows:
                if cart.quantity > product.stock:
                    raise CommerceError(f"{product.name} 库存不足")
            suffix = str(int(uuid4().hex[:4], 16) % 10000).zfill(4)
            order_id = f"SC{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
            total = sum(cart.quantity * product.price_cents for cart, product in rows)
            order = CommerceOrderRecord(
                order_id=order_id, user_id=user_id, status="pending_payment", payment_status="pending",
                shipping_status="not_shipped", total_cents=total,
                address_json=json.dumps(self._address(address), ensure_ascii=False),
            )
            session.add(order)
            session.flush()
            for cart, product in rows:
                session.add(CommerceOrderItemRecord(order_id=order_id, product_id=product.product_id, product_name=product.name, image_url=product.image_url, price_cents=product.price_cents, quantity=cart.quantity))
                session.delete(cart)
            session.add(PaymentRecord(payment_id=f"PAY-{uuid4().hex[:10].upper()}", order_id=order_id, amount_cents=total))
            session.commit()
        return self.get_order(order_id, user_id)

    def pay_order(self, order_id: str, user_id: str, success: bool) -> dict:
        with self.database.session_factory() as session:
            order = session.get(CommerceOrderRecord, order_id)
            if not order or order.user_id != user_id:
                raise CommerceError("订单不存在")
            if order.payment_status == "paid":
                return self.get_order(order_id, user_id)
            payment = session.scalar(select(PaymentRecord).where(PaymentRecord.order_id == order_id))
            if not success:
                payment.status = "failed"
                order.payment_status = "failed"
                session.commit()
                return self.get_order(order_id, user_id)
            items = session.scalars(select(CommerceOrderItemRecord).where(CommerceOrderItemRecord.order_id == order_id)).all()
            for item in items:
                product = session.get(ProductRecord, item.product_id)
                if product.stock < item.quantity:
                    raise CommerceError(f"{product.name} 库存不足")
                product.stock -= item.quantity
            now = datetime.now(timezone.utc)
            payment.status = "paid"; payment.paid_at = now
            order.status = "paid"; order.payment_status = "paid"; order.shipping_status = "preparing"; order.paid_at = now
            session.add(ShipmentRecord(
                shipment_id=f"SHP-{uuid4().hex[:10].upper()}", order_id=order_id, carrier="顺丰速运",
                tracking_number=f"SF{datetime.now().strftime('%H%M%S')}{order_id[-6:]}", status="preparing",
                latest_event="商家正在备货", events_json=json.dumps([{"status": "preparing", "content": "商家正在备货", "at": now.isoformat()}], ensure_ascii=False),
            ))
            session.commit()
        return self.get_order(order_id, user_id)

    def list_orders(self, user_id: str | None = None) -> list[dict]:
        with self.database.session_factory() as session:
            query = select(CommerceOrderRecord)
            if user_id:
                query = query.where(CommerceOrderRecord.user_id == user_id)
            ids = [item.order_id for item in session.scalars(query.order_by(CommerceOrderRecord.created_at.desc())).all()]
        return [self.get_order(order_id, user_id) for order_id in ids]

    def get_order(self, order_id: str, user_id: str | None = None) -> dict | None:
        with self.database.session_factory() as session:
            order = session.get(CommerceOrderRecord, order_id)
            if not order or (user_id and order.user_id != user_id):
                return None
            items = session.scalars(select(CommerceOrderItemRecord).where(CommerceOrderItemRecord.order_id == order_id)).all()
            shipment = session.scalar(select(ShipmentRecord).where(ShipmentRecord.order_id == order_id))
            payment = session.scalar(select(PaymentRecord).where(PaymentRecord.order_id == order_id))
            return {
                "order_id": order.order_id, "user_id": order.user_id, "status": order.status,
                "payment_status": order.payment_status, "shipping_status": order.shipping_status,
                "total_cents": order.total_cents, "address": json.loads(order.address_json),
                "created_at": utc_iso(order.created_at), "paid_at": utc_iso(order.paid_at),
                "items": [{"product_id": item.product_id, "name": item.product_name, "image_url": item.image_url, "price_cents": item.price_cents, "quantity": item.quantity} for item in items],
                "payment": {"payment_id": payment.payment_id, "status": payment.status, "method": payment.method} if payment else None,
                "shipment": {"carrier": shipment.carrier, "tracking_number": shipment.tracking_number, "status": shipment.status, "latest_event": shipment.latest_event, "events": json.loads(shipment.events_json)} if shipment else None,
            }

    def tool_order(self, order_id: str, user_id: str) -> dict:
        order = self.get_order(order_id, user_id)
        if not order:
            raise CommerceError("未找到该订单或无权查看")
        return {
            "order_id": order["order_id"], "user_id": order["user_id"],
            "product_name": "、".join(item["name"] for item in order["items"]),
            "amount": order["total_cents"] / 100, "status": order["status"],
            "created_at": order["created_at"], "delivered_at": None,
            "refundable": True,
        }

    def tool_shipment(self, order_id: str, user_id: str) -> dict:
        order = self.get_order(order_id, user_id)
        if not order:
            raise CommerceError("未找到该订单或无权查看")
        if not order["shipment"]:
            raise CommerceError("该订单暂时没有物流信息")
        shipment = order["shipment"]
        address = order["address"]
        province = str(address.get("province", ""))
        city = str(address.get("city", ""))
        if "上海" in province:
            distance_level, distance_description, eta_min, eta_max = "same_city", "上海同城配送，仓库到收货城市距离较近", 1, 2
        elif any(region in province for region in ("江苏", "浙江", "安徽")):
            distance_level, distance_description, eta_min, eta_max = "nearby", "收货地与上海嘉定仓相邻，属于近距离跨省配送", 1, 3
        elif any(region in province for region in ("新疆", "西藏", "青海", "甘肃", "宁夏", "内蒙古")):
            distance_level, distance_description, eta_min, eta_max = "remote", "收货地距离上海嘉定仓较远，属于偏远地区配送", 3, 7
        else:
            distance_level, distance_description, eta_min, eta_max = "cross_region", "收货地与上海嘉定仓跨区域，属于中长距离配送", 2, 5
        today = datetime.now(timezone.utc).date()
        return {
            **shipment,
            "order_id": order_id,
            "updated_at": order["paid_at"] or order["created_at"],
            "fulfillment_origin": "上海嘉定仓",
            "destination": {"province": province, "city": city},
            "distance_level": distance_level,
            "distance_description": distance_description,
            "eta_min_days": eta_min,
            "eta_max_days": eta_max,
            "estimated_arrival_start": (today + timedelta(days=eta_min)).isoformat(),
            "estimated_arrival_end": (today + timedelta(days=eta_max)).isoformat(),
        }

    def evaluate_refund(self, order_id: str, user_id: str) -> dict:
        order = self.get_order(order_id, user_id)
        if not order:
            raise CommerceError("未找到该订单或无权查看")
        if order["status"] not in {"paid", "shipped", "delivered"}:
            return {"eligible": False, "reason": "当前订单状态不支持退款", "requires_approval": False}
        amount = order["total_cents"] / 100
        return {"eligible": True, "reason": "订单符合基础退款条件", "requires_approval": amount >= 1000, "amount": amount}

    def create_refund(self, order_id: str, user_id: str) -> dict:
        evaluation = self.evaluate_refund(order_id, user_id)
        if not evaluation["eligible"]:
            raise CommerceError(evaluation["reason"])
        if evaluation["requires_approval"]:
            raise CommerceError("高金额退款必须由人工客服审批")
        with self.database.session_factory() as session:
            existing = session.scalar(select(RefundRecord).where(RefundRecord.order_id == order_id))
            if existing:
                return {"refund_id": existing.refund_id, "order_id": order_id, "status": existing.status, "created_at": utc_iso(existing.created_at)}
            record = RefundRecord(
                refund_id=f"RF-{uuid4().hex[:12].upper()}", order_id=order_id, user_id=user_id,
                amount_cents=int(evaluation["amount"] * 100), status="submitted",
            )
            session.add(record); session.commit(); session.refresh(record)
            return {"refund_id": record.refund_id, "order_id": order_id, "status": record.status, "created_at": utc_iso(record.created_at)}

    def create_appeal(self, order_id: str, user_id: str, payload: dict) -> dict:
        if not self.get_order(order_id, user_id):
            raise CommerceError("订单不存在或无权申诉")
        with self.database.session_factory() as session:
            record = AppealRecord(
                appeal_id=f"AP-{uuid4().hex[:10].upper()}", order_id=order_id, user_id=user_id,
                priority="high" if payload["appeal_type"] in {"rights_protection", "refund"} else "normal",
                status="submitted", **payload,
            )
            session.add(record); session.flush()
            self._add_event(session, record, user_id, "顾客", "customer", "submitted", "用户提交申诉", {}, None, "submitted")
            session.commit()
            return self.get_appeal(record.appeal_id, user_id)

    def list_appeals(self, user_id: str | None = None) -> list[dict]:
        with self.database.session_factory() as session:
            query = select(AppealRecord)
            if user_id:
                query = query.where(AppealRecord.user_id == user_id)
            appeal_ids = [item.appeal_id for item in session.scalars(query.order_by(AppealRecord.created_at.desc())).all()]
        return [item for appeal_id in appeal_ids if (item := self.get_appeal(appeal_id, user_id))]

    def get_appeal(self, appeal_id: str, user_id: str | None = None) -> dict | None:
        with self.database.session_factory() as session:
            record = session.get(AppealRecord, appeal_id)
            if not record or (user_id and record.user_id != user_id):
                return None
            result = self._appeal(record)
            result["attachments"] = [self._attachment(item) for item in session.scalars(select(AppealAttachmentRecord).where(AppealAttachmentRecord.appeal_id == appeal_id).order_by(AppealAttachmentRecord.created_at)).all()]
            result["material_requests"] = [self._material_request(item) for item in session.scalars(select(AppealMaterialRequestRecord).where(AppealMaterialRequestRecord.appeal_id == appeal_id).order_by(AppealMaterialRequestRecord.created_at)).all()]
            events_query = select(AppealEventRecord).where(AppealEventRecord.appeal_id == appeal_id)
            if user_id:
                events_query = events_query.where(AppealEventRecord.visible_to_customer == 1)
            result["events"] = [self._event_record(item) for item in session.scalars(events_query.order_by(AppealEventRecord.created_at)).all()]
            executions = session.scalars(
                select(AppealExecutionRecord)
                .where(AppealExecutionRecord.appeal_id == appeal_id)
                .order_by(AppealExecutionRecord.approval_round, AppealExecutionRecord.created_at)
            ).all()
            result["executions"] = [self._execution(item) for item in executions]
            result["execution"] = self._execution(executions[-1]) if executions else None
            order = session.get(CommerceOrderRecord, record.order_id)
            result["order_total_cents"] = order.total_cents if order else 0
            return result

    def attach_appeal_result(self, appeal_id: str, ticket_id: str | None, result: dict) -> dict:
        with self.database.session_factory() as session:
            record = session.get(AppealRecord, appeal_id)
            if not record:
                raise CommerceError("申诉不存在")
            record.ticket_id = ticket_id
            record.agent_result_json = json.dumps(result, ensure_ascii=False)
            record.updated_at = datetime.now(timezone.utc)
            existing = session.scalar(select(AppealEventRecord).where(AppealEventRecord.appeal_id == appeal_id, AppealEventRecord.event_type == "initial_review"))
            if not existing:
                self._add_event(session, record, "system", "系统", "system", "initial_review", "智能核验已完成", {"summary": result.get("answer", "")}, record.status, record.status)
            session.commit()
        return self.get_appeal(appeal_id)

    def add_appeal_attachment(self, appeal_id: str, user_id: str, values: dict) -> dict:
        with self.database.session_factory() as session:
            appeal = session.get(AppealRecord, appeal_id)
            if not appeal or appeal.user_id != user_id:
                raise CommerceError("申诉不存在或无权上传附件")
            material_request_id = values.get("material_request_id")
            material_request = None
            if material_request_id:
                material_request = session.get(AppealMaterialRequestRecord, material_request_id)
                if not material_request or material_request.appeal_id != appeal_id:
                    raise CommerceError("补材料要求不存在")
                if material_request.status not in {"pending", "submitted"}:
                    raise CommerceError("该补材料要求已经完成")
            elif appeal.status == "waiting_customer":
                material_request = session.scalar(
                    select(AppealMaterialRequestRecord).where(
                        AppealMaterialRequestRecord.appeal_id == appeal_id,
                        AppealMaterialRequestRecord.status == "pending",
                    ).order_by(AppealMaterialRequestRecord.created_at.desc())
                )
                values["material_request_id"] = material_request.request_id if material_request else None
            record = AppealAttachmentRecord(
                attachment_id=f"ATT-{uuid4().hex[:12].upper()}", appeal_id=appeal_id, user_id=user_id, **values,
            )
            session.add(record)
            old_status = appeal.status
            if appeal.status == "waiting_customer":
                appeal.status = "investigating"
            if material_request:
                material_request.status = "submitted"
                material_request.completed_at = None
            self._add_event(
                session, appeal, user_id, "顾客", "customer", "attachment_uploaded", "用户补充了证据材料",
                {"file_name": record.file_name, "material_request_id": values.get("material_request_id")},
                old_status, appeal.status,
            )
            session.commit(); session.refresh(record)
            return self._attachment(record)

    def accept_appeal(self, appeal_id: str, actor_id: str, actor_name: str) -> dict:
        with self.database.session_factory() as session:
            record = self._require_appeal(session, appeal_id)
            if record.status != "submitted":
                raise CommerceError("只有待受理申诉可以接单")
            old = record.status
            record.status, record.assigned_to, record.assigned_name = "investigating", actor_id, actor_name
            record.accepted_at = datetime.now(timezone.utc)
            self._add_event(session, record, actor_id, actor_name, "agent", "accepted", f"{actor_name} 已受理申诉", {}, old, record.status)
            session.commit()
        return self.get_appeal(appeal_id)

    def request_material(self, appeal_id: str, actor_id: str, actor_name: str, content: str, due_at: datetime | None) -> dict:
        with self.database.session_factory() as session:
            record = self._require_assignee(session, appeal_id, actor_id)
            if record.status not in {"investigating", "returned"}:
                raise CommerceError("当前状态不能要求补充材料")
            old = record.status; record.status = "waiting_customer"
            request = AppealMaterialRequestRecord(request_id=f"MR-{uuid4().hex[:10].upper()}", appeal_id=appeal_id, content=content, requested_by=actor_id, requested_name=actor_name, due_at=due_at)
            session.add(request)
            self._add_event(session, record, actor_id, actor_name, "agent", "material_requested", "客服要求补充材料", {"content": content, "due_at": utc_iso(due_at)}, old, record.status)
            session.commit()
        return self.get_appeal(appeal_id)

    def review_attachment(self, appeal_id: str, attachment_id: str, actor_id: str, actor_name: str, status: str, note: str) -> dict:
        with self.database.session_factory() as session:
            record = self._require_assignee(session, appeal_id, actor_id)
            attachment = session.get(AppealAttachmentRecord, attachment_id)
            if not attachment or attachment.appeal_id != appeal_id:
                raise CommerceError("附件不存在")
            attachment.review_status, attachment.reviewed_by, attachment.reviewed_name = status, actor_id, actor_name
            attachment.review_note, attachment.reviewed_at = note, datetime.now(timezone.utc)
            old_status = record.status
            material_request = session.get(AppealMaterialRequestRecord, attachment.material_request_id) if attachment.material_request_id else None
            if material_request:
                material_request.status = "completed" if status == "accepted" else "pending"
                material_request.completed_at = datetime.now(timezone.utc) if status == "accepted" else None
                if status == "rejected":
                    record.status = "waiting_customer"
            title = "补充材料审核通过" if status == "accepted" else "补充材料审核未通过"
            self._add_event(
                session, record, actor_id, actor_name, "agent", "attachment_reviewed", title,
                {"attachment_id": attachment_id, "material_request_id": attachment.material_request_id, "status": status, "note": note},
                old_status, record.status, True,
            )
            session.commit()
        return self.get_appeal(appeal_id)

    def save_investigation(self, appeal_id: str, actor_id: str, actor_name: str, responsibility: str, conclusion: str) -> dict:
        with self.database.session_factory() as session:
            record = self._require_assignee(session, appeal_id, actor_id)
            if record.status not in {"investigating", "returned"}:
                raise CommerceError("当前状态不能填写调查结论")
            record.responsibility, record.investigation_conclusion, record.status = responsibility, conclusion, "investigating"
            self._add_event(session, record, actor_id, actor_name, "agent", "investigation_saved", "调查结论已更新", {"responsibility": responsibility}, record.status, record.status, False)
            session.commit()
        return self.get_appeal(appeal_id)

    def save_proposal(self, appeal_id: str, actor_id: str, actor_name: str, action: str, amount_cents: int | None, reason: str) -> dict:
        with self.database.session_factory() as session:
            record = self._require_assignee(session, appeal_id, actor_id)
            if record.status not in {"investigating", "returned"} or not record.investigation_conclusion or not record.responsibility:
                raise CommerceError("请先完成责任认定和调查结论")
            order = session.get(CommerceOrderRecord, record.order_id)
            if action in {"refund", "return_refund", "compensation"}:
                if amount_cents is None or amount_cents <= 0:
                    raise CommerceError("资金类方案必须填写金额")
                if not order or amount_cents > order.total_cents:
                    raise CommerceError("方案金额不能超过订单实付金额")
            else:
                amount_cents = None
            record.proposed_action, record.proposed_amount_cents, record.proposal_reason = action, amount_cents, reason
            record.risk_level = "high" if action in {"refund", "return_refund", "compensation", "reject"} or record.priority == "high" else "medium"
            reasons = ["高风险申诉方案需要全权限管理员确认后执行"]
            if amount_cents and amount_cents >= 100000:
                reasons.append("方案金额达到高金额审核阈值")
            record.risk_reasons_json = json.dumps(reasons, ensure_ascii=False)
            record.approved_by = record.approved_name = record.approval_comment = None
            record.approved_at = None
            self._add_event(session, record, actor_id, actor_name, "agent", "proposal_saved", "处理方案已拟定", {"action": action, "amount_cents": amount_cents}, record.status, record.status, False)
            session.commit()
        return self.get_appeal(appeal_id)

    def submit_appeal_approval(self, appeal_id: str, actor_id: str, actor_name: str) -> dict:
        with self.database.session_factory() as session:
            record = self._require_assignee(session, appeal_id, actor_id)
            if record.status not in {"investigating", "returned"} or not record.proposed_action:
                raise CommerceError("请先完成处理方案")
            old = record.status; record.status = "pending_approval"; record.submitted_for_approval_at = datetime.now(timezone.utc)
            self._add_event(session, record, actor_id, actor_name, "agent", "approval_submitted", "处理方案已进入管理员确认流程", {}, old, record.status)
            session.commit()
        return self.get_appeal(appeal_id)

    def approve_appeal(self, appeal_id: str, admin_id: str, admin_name: str, decision: str, comment: str) -> dict:
        with self.database.session_factory() as session:
            record = self._require_appeal(session, appeal_id)
            if record.status != "pending_approval":
                raise CommerceError("当前申诉不在待审批状态")
            old = record.status
            record.approval_comment = comment
            if decision == "return":
                record.status = "returned"
                self._add_event(session, record, admin_id, admin_name, "admin", "approval_returned", "管理员退回处理方案", {"comment": comment}, old, record.status)
                session.commit()
            else:
                record.status, record.approved_by, record.approved_name = "executing", admin_id, admin_name
                record.approved_at = datetime.now(timezone.utc)
                self._add_event(session, record, admin_id, admin_name, "admin", "approval_approved", "管理员已批准处理方案", {"comment": comment}, old, record.status)
                session.commit()
        if decision == "approve":
            self.execute_appeal(appeal_id)
        return self.get_appeal(appeal_id)

    def execute_appeal(self, appeal_id: str) -> dict:
        with self.database.session_factory() as session:
            record = self._require_appeal(session, appeal_id)
            executions = session.scalars(
                select(AppealExecutionRecord)
                .where(AppealExecutionRecord.appeal_id == appeal_id)
                .order_by(AppealExecutionRecord.approval_round.desc())
            ).all()
            latest = executions[0] if executions else None
            if latest and record.status not in {"executing", "execution_failed"}:
                return self.get_appeal(appeal_id)
            if record.status not in {"executing", "execution_failed"} or not record.approved_by:
                raise CommerceError("方案尚未审批，不能执行")
            try:
                reference = f"SBX-{uuid4().hex[:12].upper()}"
                if record.proposed_action in {"refund", "return_refund"}:
                    refund = session.scalar(select(RefundRecord).where(RefundRecord.order_id == record.order_id))
                    if not refund:
                        refund = RefundRecord(refund_id=f"RF-{uuid4().hex[:12].upper()}", order_id=record.order_id, user_id=record.user_id, amount_cents=record.proposed_amount_cents or 0, status="submitted")
                        session.add(refund)
                    reference = refund.refund_id
                result_json = json.dumps({"sandbox": True, "message": "沙箱业务单已创建，不产生真实资金交易"}, ensure_ascii=False)
                if record.status == "execution_failed" and latest and latest.status == "failed":
                    latest.action, latest.amount_cents, latest.status = record.proposed_action or "unknown", record.proposed_amount_cents, "completed"
                    latest.sandbox_reference, latest.result_json, latest.error_message = reference, result_json, None
                    execution_round = latest.approval_round
                else:
                    execution_round = (latest.approval_round + 1) if latest else 1
                    session.add(AppealExecutionRecord(
                        execution_id=f"EX-{uuid4().hex[:12].upper()}", appeal_id=appeal_id,
                        approval_round=execution_round, action=record.proposed_action or "unknown",
                        amount_cents=record.proposed_amount_cents, status="completed",
                        sandbox_reference=reference, result_json=result_json,
                    ))
                old = record.status; record.status = "waiting_confirmation"
                self._add_event(session, record, "system", "系统", "system", "execution_completed", "沙箱处理已完成，等待用户确认", {"reference": reference, "action": record.proposed_action, "approval_round": execution_round}, old, record.status)
                session.commit()
            except Exception as exc:
                record.status = "execution_failed"
                self._add_event(session, record, "system", "系统", "system", "execution_failed", "沙箱业务单执行失败", {"error": str(exc)}, "executing", record.status, False)
                session.commit()
                raise CommerceError("沙箱业务单执行失败") from exc
        return self.get_appeal(appeal_id)

    def customer_feedback(self, appeal_id: str, user_id: str, confirmation: str, comment: str) -> dict:
        with self.database.session_factory() as session:
            record = self._require_appeal(session, appeal_id)
            if record.user_id != user_id or record.status != "waiting_confirmation":
                raise CommerceError("当前申诉不能确认处理结果")
            old = record.status; record.customer_confirmation = confirmation
            if confirmation == "confirmed":
                record.status, record.resolved_at = "resolved", datetime.now(timezone.utc)
                title, event_type = "用户已确认处理结果，申诉结案", "customer_confirmed"
            else:
                record.status = "investigating"
                title, event_type = "用户对处理结果提出异议", "customer_objected"
            self._add_event(session, record, user_id, "顾客", "customer", event_type, title, {"comment": comment}, old, record.status)
            session.commit()
        return self.get_appeal(appeal_id, user_id)

    @staticmethod
    def _require_appeal(session, appeal_id: str) -> AppealRecord:
        record = session.get(AppealRecord, appeal_id)
        if not record:
            raise CommerceError("申诉不存在")
        return record

    def _require_assignee(self, session, appeal_id: str, actor_id: str) -> AppealRecord:
        record = self._require_appeal(session, appeal_id)
        if record.assigned_to != actor_id:
            raise CommerceError("只有当前负责人可以推进该申诉")
        return record

    @staticmethod
    def _add_event(session, appeal: AppealRecord, actor_id: str, actor_name: str, actor_role: str, event_type: str, title: str, detail: dict, from_status: str | None, to_status: str | None, visible: bool = True) -> None:
        session.add(AppealEventRecord(appeal_id=appeal.appeal_id, actor_id=actor_id, actor_name=actor_name, actor_role=actor_role, event_type=event_type, title=title, detail_json=json.dumps(detail, ensure_ascii=False), from_status=from_status, to_status=to_status, visible_to_customer=1 if visible else 0))

    def list_appeal_attachments(self, appeal_id: str, user_id: str | None = None) -> list[dict]:
        with self.database.session_factory() as session:
            query = select(AppealAttachmentRecord).where(AppealAttachmentRecord.appeal_id == appeal_id)
            if user_id:
                query = query.where(AppealAttachmentRecord.user_id == user_id)
            return [self._attachment(item) for item in session.scalars(query.order_by(AppealAttachmentRecord.created_at)).all()]

    def get_attachment(self, attachment_id: str) -> dict | None:
        with self.database.session_factory() as session:
            item = session.get(AppealAttachmentRecord, attachment_id)
            return self._attachment(item) if item else None

    @staticmethod
    def _product(item: ProductRecord) -> dict:
        return {"product_id": item.product_id, "name": item.name, "category": item.category, "description": item.description, "price_cents": item.price_cents, "stock": item.stock, "image_url": item.image_url, "specs": json.loads(item.specs_json), "warranty_months": item.warranty_months}

    @staticmethod
    def _address(item: AddressRecord) -> dict:
        return {"address_id": item.address_id, "recipient": item.recipient, "phone": item.phone, "province": item.province, "city": item.city, "detail": item.detail, "is_default": bool(item.is_default)}

    @staticmethod
    def _appeal(item: AppealRecord) -> dict:
        return {"appeal_id": item.appeal_id, "order_id": item.order_id, "user_id": item.user_id, "session_id": item.session_id, "ticket_id": item.ticket_id, "appeal_type": item.appeal_type, "description": item.description, "priority": item.priority, "status": item.status, "agent_result": json.loads(item.agent_result_json) if item.agent_result_json else None, "assigned_to": item.assigned_to, "assigned_name": item.assigned_name, "accepted_at": utc_iso(item.accepted_at), "responsibility": item.responsibility, "investigation_conclusion": item.investigation_conclusion, "proposed_action": item.proposed_action, "proposed_amount_cents": item.proposed_amount_cents, "proposal_reason": item.proposal_reason, "risk_level": item.risk_level, "risk_reasons": json.loads(item.risk_reasons_json or "[]"), "submitted_for_approval_at": utc_iso(item.submitted_for_approval_at), "approved_by": item.approved_by, "approved_name": item.approved_name, "approval_comment": item.approval_comment, "approved_at": utc_iso(item.approved_at), "customer_confirmation": item.customer_confirmation, "resolved_at": utc_iso(item.resolved_at), "created_at": utc_iso(item.created_at), "updated_at": utc_iso(item.updated_at)}

    @staticmethod
    def _attachment(item: AppealAttachmentRecord) -> dict:
        return {"attachment_id": item.attachment_id, "appeal_id": item.appeal_id, "material_request_id": item.material_request_id, "user_id": item.user_id, "file_name": item.file_name, "content_type": item.content_type, "storage_path": item.storage_path, "size_bytes": item.size_bytes, "review_status": item.review_status, "reviewed_name": item.reviewed_name, "review_note": item.review_note, "reviewed_at": utc_iso(item.reviewed_at), "created_at": utc_iso(item.created_at)}

    @staticmethod
    def _event_record(item: AppealEventRecord) -> dict:
        return {"id": item.id, "actor_name": item.actor_name, "actor_role": item.actor_role, "event_type": item.event_type, "title": item.title, "detail": json.loads(item.detail_json or "{}"), "from_status": item.from_status, "to_status": item.to_status, "visible_to_customer": bool(item.visible_to_customer), "created_at": utc_iso(item.created_at)}

    @staticmethod
    def _material_request(item: AppealMaterialRequestRecord) -> dict:
        return {"request_id": item.request_id, "content": item.content, "status": item.status, "requested_name": item.requested_name, "due_at": utc_iso(item.due_at), "completed_at": utc_iso(item.completed_at), "created_at": utc_iso(item.created_at)}

    @staticmethod
    def _execution(item: AppealExecutionRecord) -> dict:
        return {"execution_id": item.execution_id, "approval_round": item.approval_round, "action": item.action, "amount_cents": item.amount_cents, "status": item.status, "sandbox_reference": item.sandbox_reference, "result": json.loads(item.result_json or "{}"), "error_message": item.error_message, "created_at": utc_iso(item.created_at), "updated_at": utc_iso(item.updated_at)}
