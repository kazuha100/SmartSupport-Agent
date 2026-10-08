import re

from app.llm import ChatModel, ModelError
from app.models import ChatResponse, ToolCall, TraceStep
from app.rag.retriever import KnowledgeBase
from app.routing import SHIPMENT_TERMS, is_general_chat, requires_human_handoff
from app.tools.business import BusinessRuleError, create_refund, evaluate_refund, get_order, get_shipment


ORDER_PATTERN = re.compile(r"(?:XY\d{8}|SC\d{18})", re.IGNORECASE)
PRODUCT_PATTERN = re.compile(r"P-[A-Z0-9]+", re.IGNORECASE)


class SupportAgent:
    def __init__(self, knowledge_base: KnowledgeBase, chat_model: ChatModel | None = None):
        self.knowledge_base = knowledge_base
        self.chat_model = chat_model

    def respond(self, message: str, user_id: str) -> ChatResponse:
        normalized = message.strip()
        order_match = ORDER_PATTERN.search(normalized.upper())
        order_id = order_match.group(0).upper() if order_match else None
        product_match = PRODUCT_PATTERN.search(normalized.upper())
        product_id = product_match.group(0).upper() if product_match else None
        trace = [TraceStep(name="意图识别", detail="正在判断知识问答、业务查询或人工服务请求。")]

        if requires_human_handoff(normalized):
            trace.append(TraceStep(name="人工转接", detail="用户明确要求人工服务。"))
            return ChatResponse(
                answer="已为你创建人工服务请求。客服接管前，我会保留当前会话内容。",
                intent="human_handoff",
                confidence=1.0,
                needs_human=True,
                trace=trace,
            )

        if is_general_chat(normalized):
            answer = self._friendly_general_reply(normalized)
            if self.chat_model:
                try:
                    answer = self.chat_model.answer_general(normalized)
                    trace.append(
                        TraceStep(name="DeepSeek 通用对话", detail=f"已使用 {self.chat_model.model} 回答普通对话。")
                    )
                except ModelError:
                    trace.append(
                        TraceStep(name="模型降级", detail="DeepSeek 暂时不可用，已使用通用客服回复。", status="blocked")
                    )
            return ChatResponse(answer=answer, intent="general_chat", confidence=0.96, trace=trace)

        if any(term in normalized for term in SHIPMENT_TERMS):
            return self._shipment(normalized, order_id, user_id, trace)

        if any(term in normalized for term in ("退款", "退货", "退钱")) and order_id:
            return self._refund(normalized, order_id, user_id, trace)

        if order_id and any(term in normalized for term in ("订单", "查询", "状态")):
            return self._order(order_id, user_id, trace)

        citations = self.knowledge_base.search(normalized, product_id=product_id)
        trace.append(
            TraceStep(
                name="知识检索",
                detail=f"找到 {len(citations)} 条相关知识片段。" if citations else "没有找到可靠的知识依据。",
                status="done" if citations else "blocked",
            )
        )
        if not citations:
            answer = self._friendly_general_reply(normalized)
            if self.chat_model:
                try:
                    answer = self.chat_model.answer_general(normalized)
                    trace.append(
                        TraceStep(name="DeepSeek 通用对话", detail=f"已使用 {self.chat_model.model} 回答非业务闲聊。")
                    )
                except ModelError:
                    trace.append(
                        TraceStep(name="模型降级", detail="DeepSeek 暂时不可用，已使用通用客服回复。", status="blocked")
                    )
            return ChatResponse(
                answer=answer,
                intent="general_chat",
                confidence=0.82,
                trace=trace,
            )
        answer = f"根据《{citations[0].title}》：{citations[0].excerpt}"
        if self.chat_model:
            try:
                answer = self.chat_model.answer_with_sources(normalized, citations)
                trace.append(
                    TraceStep(
                        name="DeepSeek 生成",
                        detail=f"已使用 {self.chat_model.model} 基于检索资料生成回答。",
                    )
                )
            except ModelError:
                trace.append(
                    TraceStep(
                        name="模型降级",
                        detail="DeepSeek 暂时不可用，已使用确定性知识摘要回答。",
                        status="blocked",
                    )
                )
        return ChatResponse(
            answer=answer,
            intent="knowledge_qa",
            confidence=min(0.95, 0.68 + citations[0].score * 0.22),
            citations=citations,
            trace=trace,
        )

    def _order(self, order_id: str, user_id: str, trace: list[TraceStep]) -> ChatResponse:
        try:
            order = get_order(order_id, user_id)
            tool = ToolCall(
                name="get_order",
                status="success",
                arguments={"order_id": order_id},
                summary=f"订单状态：{order['status']}，金额：¥{order['amount']:.2f}",
            )
            trace.append(TraceStep(name="订单工具", detail="已完成订单归属校验并读取订单。"))
            return ChatResponse(
                answer=f"订单 {order_id} 的商品是{order['product_name']}，当前状态为 {order['status']}，订单金额 ¥{order['amount']:.2f}。",
                intent="order_query",
                confidence=0.99,
                tool_calls=[tool],
                trace=trace,
            )
        except BusinessRuleError as exc:
            return self._tool_error("get_order", order_id, str(exc), "order_query", trace)

    def _shipment(self, message: str, order_id: str | None, user_id: str, trace: list[TraceStep]) -> ChatResponse:
        if not order_id:
            trace.append(TraceStep(name="物流工具", detail="缺少订单号，等待用户补充。", status="waiting"))
            return ChatResponse(
                answer="请提供商城订单号，我才能查询物流。",
                intent="shipment_query",
                confidence=0.94,
                trace=trace,
            )
        try:
            citations = self.knowledge_base.search("配送时效 发货仓库 预计送达 物流异常", limit=2)
            trace.append(TraceStep(
                name="配送知识检索",
                detail=f"已检索到 {len(citations)} 条配送时效与异常处理依据。" if citations else "未检索到配送时效依据。",
                status="done" if citations else "blocked",
            ))
            shipment = get_shipment(order_id, user_id)
            tool = ToolCall(
                name="get_shipment",
                status="success",
                arguments={"order_id": order_id},
                summary=f"{shipment['latest_event']}，预计 {shipment['eta_min_days']}-{shipment['eta_max_days']} 天送达",
            )
            destination = "".join(filter(None, (shipment["destination"]["province"], shipment["destination"]["city"]))) or "收货地区"
            trace.append(TraceStep(name="物流工具", detail="已校验订单归属，并读取物流轨迹、发货仓和收货地区。"))
            trace.append(TraceStep(name="距离与时效估算", detail=f"{shipment['distance_description']}，预计 {shipment['eta_min_days']}-{shipment['eta_max_days']} 天。"))
            source = "[资料1]" if citations else ""
            if shipment["status"] == "delivered" or "已签收" in shipment["latest_event"]:
                answer = f"我帮你核对过了，订单 {order_id} 已经送达，最新物流记录是“{shipment['latest_event']}”。如果你还没有收到，可以告诉我具体情况，我再帮你发起物流核查。"
            else:
                answer = (
                    f"我先帮你查了订单物流和商城配送规则。订单 {order_id} 目前由{shipment['carrier']}配送，"
                    f"最新进度是“{shipment['latest_event']}”。\n"
                    f"这件商品从{shipment['fulfillment_origin']}发往{destination}，{shipment['distance_description']}。"
                    f"结合当前节点，预计还需要 {shipment['eta_min_days']}-{shipment['eta_max_days']} 天，"
                    f"预计送达区间为 {shipment['estimated_arrival_start']} 至 {shipment['estimated_arrival_end']}。{source}\n"
                    "这个时间是根据仓库距离和配送规则估算的，实际以承运商轨迹为准；如果物流超过 48 小时没有更新，我可以继续帮你发起物流核查。"
                )
            if self.chat_model:
                grounded_context = (
                    f"用户原问题：{message}\n"
                    f"已核实订单数据：订单号={order_id}；承运商={shipment['carrier']}；最新节点={shipment['latest_event']}；"
                    f"发货仓={shipment['fulfillment_origin']}；收货省市={destination}；"
                    f"距离判断={shipment['distance_description']}；预计还需={shipment['eta_min_days']}-{shipment['eta_max_days']}天；"
                    f"预计送达={shipment['estimated_arrival_start']}至{shipment['estimated_arrival_end']}。\n"
                    "请基于这些已核实数据和配送资料，用自然的中文回复用户，说明查询依据、当前进度、预计区间和物流超过48小时未更新时的处理方式。"
                    "不要编造精确公里数，不要改变已核实的日期和天数，回答至少两句话。"
                )
                try:
                    answer = self.chat_model.answer_with_sources(grounded_context, citations)
                    trace.append(TraceStep(name="DeepSeek 物流回复", detail=f"已使用 {self.chat_model.model} 基于订单工具和配送知识生成回复。"))
                except ModelError:
                    trace.append(TraceStep(name="模型降级", detail="DeepSeek 暂时不可用，已使用订单数据和配送规则生成回复。", status="blocked"))
            return ChatResponse(
                answer=answer,
                intent="shipment_query",
                confidence=0.97 if citations else 0.88,
                citations=citations,
                tool_calls=[tool],
                trace=trace,
            )
        except BusinessRuleError as exc:
            return self._tool_error("get_shipment", order_id, str(exc), "shipment_query", trace)

    @staticmethod
    def _friendly_general_reply(message: str) -> str:
        lower = message.lower()
        if any(term in lower for term in ("谢谢", "感谢")):
            return "不客气，很高兴能帮到你。之后无论是想了解商品，还是查询订单和售后进度，都可以继续问我。"
        if "早上好" in lower:
            return "早上好呀，希望你今天心情不错！想看看商品，还是有订单或售后问题需要我帮忙？"
        if "下午好" in lower:
            return "下午好，很高兴见到你！你可以直接告诉我想咨询的商品或订单问题，我来帮你查。"
        if "晚上好" in lower:
            return "晚上好呀，这个时间我也在线。你想咨询商品、订单进度，还是售后问题？"
        if any(term in lower for term in ("在吗", "在不在")):
            return "在的，我一直在线。你直接说遇到了什么问题，我会先帮你查清楚再回复。"
        if any(term in lower for term in ("再见", "拜拜")):
            return "好的，感谢你的咨询。之后有商品、订单或售后问题，随时回来找我。"
        return "你好呀，很高兴见到你！今天想了解哪款商品，还是需要我帮你查询订单或售后进度？"

    def _refund(self, message: str, order_id: str, user_id: str, trace: list[TraceStep]) -> ChatResponse:
        try:
            evaluation = evaluate_refund(order_id, user_id)
            trace.append(TraceStep(name="退款规则", detail=evaluation["reason"]))
            evaluation_call = ToolCall(
                name="evaluate_refund",
                status="success",
                arguments={"order_id": order_id},
                summary=evaluation["reason"],
            )
            if not evaluation["eligible"]:
                return ChatResponse(
                    answer=f"订单 {order_id} 暂不符合自动退款条件：{evaluation['reason']}。",
                    intent="refund_request",
                    confidence=0.98,
                    tool_calls=[evaluation_call],
                    trace=trace,
                )
            if evaluation["requires_approval"]:
                trace.append(TraceStep(name="风险控制", detail="高金额退款需要人工审批。", status="waiting"))
                return ChatResponse(
                    answer=f"订单 {order_id} 符合基础退款条件，但金额为 ¥{evaluation['amount']:.2f}，需要人工客服审批。我已准备转接。",
                    intent="refund_request",
                    confidence=0.99,
                    needs_human=True,
                    tool_calls=[evaluation_call],
                    trace=trace,
                )
            if "确认" not in message:
                trace.append(TraceStep(name="用户确认", detail="执行退款前需要用户明确确认。", status="waiting"))
                return ChatResponse(
                    answer=f"订单 {order_id} 符合退款条件，预计退款 ¥{evaluation['amount']:.2f}。如需提交，请回复“确认退款 {order_id}”。",
                    intent="refund_request",
                    confidence=0.98,
                    tool_calls=[evaluation_call],
                    trace=trace,
                )
            refund = create_refund(order_id, user_id)
            trace.append(TraceStep(name="提交退款", detail=f"退款单 {refund['refund_id']} 已创建。"))
            return ChatResponse(
                answer=f"退款申请已提交，退款单号 {refund['refund_id']}。审核结果会通过站内消息通知你。",
                intent="refund_request",
                confidence=0.99,
                tool_calls=[
                    evaluation_call,
                    ToolCall(
                        name="create_refund",
                        status="success",
                        arguments={"order_id": order_id},
                        summary=f"退款单 {refund['refund_id']} 已提交",
                    ),
                ],
                trace=trace,
            )
        except BusinessRuleError as exc:
            return self._tool_error("evaluate_refund", order_id, str(exc), "refund_request", trace)

    @staticmethod
    def _tool_error(name: str, order_id: str, error: str, intent: str, trace: list[TraceStep]) -> ChatResponse:
        trace.append(TraceStep(name="权限与参数校验", detail=error, status="blocked"))
        return ChatResponse(
            answer=error,
            intent=intent,
            confidence=0.99,
            needs_human="无权" in error,
            tool_calls=[
                ToolCall(name=name, status="blocked", arguments={"order_id": order_id}, summary=error)
            ],
            trace=trace,
        )
