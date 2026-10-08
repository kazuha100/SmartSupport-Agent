import argparse
import json
from pathlib import Path


CATEGORY_TARGETS = {
    "general": 200,
    "returns_policy": 400,
    "logistics": 350,
    "orders": 250,
    "refund_actions": 300,
    "products_warranty": 400,
    "payment_invoice": 350,
    "account_security": 300,
    "membership": 250,
    "handoff": 150,
    "unknown": 250,
}

CATEGORY_QUESTIONS = {
    "general": [
        "你好啊", "您好，请问你是谁", "今天心情怎么样", "谢谢你的帮助", "你在吗",
        "早上好", "晚上好", "你能做什么", "很高兴认识你", "再见啦",
    ],
    "returns_policy": [
        "七天无理由退货有什么要求", "拆封后还能退货吗", "退货需要准备哪些材料",
        "商品试用后能不能退", "退货运费由谁承担", "换货需要满足什么条件",
        "商品降价后可以申请价保吗", "收到破损商品怎么处理", "退款一般多久到账",
        "赠品缺失会影响退货吗", "电子商品激活后能退吗", "换货后保修期怎么计算",
    ],
    "logistics": [
        "订单 XY20260702 到哪里了", "快递为什么一直没有更新", "配送通常需要几天",
        "包裹显示签收但我没收到", "快递配送失败怎么办", "预售商品什么时候发货",
        "能修改订单的收货地址吗", "物流卡在转运中心怎么办", "可以拒收这个包裹吗",
        "订单 XY20260701 用什么快递", "偏远地区可以配送吗", "快递丢失应该怎么处理",
    ],
    "orders": [
        "查询订单 XY20260702", "订单 XY20260701 当前是什么状态", "我想查看订单详情",
        "订单金额是多少", "订单为什么被取消", "在哪里查看历史订单",
        "订单 XY20260702 是什么商品", "订单提交后还能修改吗", "为什么找不到我的订单",
        "订单状态是什么意思",
    ],
    "refund_actions": [
        "我想退款 XY20260701", "帮我申请退款 XY20260702", "订单退款失败怎么办",
        "退款一直没到账", "取消订单后会自动退款吗", "退款可以退到其他银行卡吗",
        "订单 XY20260701 是否符合退款条件", "高金额退款为什么需要审批",
        "退款申请可以撤销吗", "部分退款应该怎么申请",
    ],
    "products_warranty": [
        "星云手机 A1 保修多久", "星云轻薄本 B2 的配置是什么", "耳机 C3 出现杂音怎么办",
        "手机进水还能免费保修吗", "笔记本电池保修多长时间", "充电器能给哪些设备使用",
        "数据线损坏属于保修吗", "耳机降噪功能异常怎么处理", "维修后还有保修吗",
        "设备被摔坏可以免费维修吗", "如何查询产品序列号", "寄修产品需要备份数据吗",
    ],
    "payment_invoice": [
        "银行卡重复扣款怎么办", "支付失败但是余额减少了", "可以使用分期付款吗",
        "如何申请电子发票", "增值税专用发票怎么开", "优惠券过期后还能使用吗",
        "订单取消后优惠券会返还吗", "发票抬头填错了能修改吗", "分期付款可以提前还款吗",
        "为什么优惠券不能使用", "可以同时使用两张优惠券吗", "退款后发票怎么处理",
    ],
    "account_security": [
        "账号被盗了怎么办", "发现异地登录应该怎么处理", "忘记密码怎么找回",
        "收不到登录验证码怎么办", "如何注销商城账号", "可以导出我的个人数据吗",
        "账号被锁定多久恢复", "怎么修改绑定手机号", "如何开启账号安全保护",
        "个人信息会保存多久",
    ],
    "membership": [
        "会员积分年底会过期吗", "消费后多久可以获得积分", "积分可以抵扣现金吗",
        "退款后积分会返还吗", "会员等级有哪些权益", "会员等级为什么下降了",
        "积分可以转给其他账号吗", "如何成为金卡会员", "生日会员有什么权益",
        "在哪里查看积分明细",
    ],
    "handoff": [
        "我要转人工客服", "请帮我联系人工", "我要投诉", "找真人客服处理",
        "重复扣款需要人工处理", "账号被盗请转人工", "退款失败我要找客服",
        "这个问题需要人工服务", "请让人工来处理", "我要联系客服",
    ],
    "unknown": [
        "量子纠缠课程怎么报名", "宠物美容服务如何预约", "商场停车位怎么申请",
        "海外留学咨询收费多少", "咖啡豆烘焙课程什么时候开课", "直播课程证书如何领取",
        "健身房月卡可以暂停吗", "酒店预订可以延迟入住吗", "电影票怎么选择座位",
        "云盘容量如何扩容", "家政保洁怎么预约", "演唱会门票什么时候开售",
    ],
}

PREFIXES = (
    "", "请问，", "想咨询一下，", "麻烦帮我确认，", "我想了解，",
    "能帮我看看吗，", "您好，", "我有个问题，", "方便说明一下吗，", "请帮忙处理，",
)
SUFFIXES = ("", "？", "，谢谢。", "，能详细说说吗？", "，应该怎么处理？")


def generate_questions() -> list[dict]:
    records: list[dict] = []
    sequence = 1
    for category, target in CATEGORY_TARGETS.items():
        generated: set[str] = set()
        for base in CATEGORY_QUESTIONS[category]:
            for prefix in PREFIXES:
                for suffix in SUFFIXES:
                    question = f"{prefix}{base.rstrip('？?。')}{suffix}".strip()
                    if question in generated:
                        continue
                    generated.add(question)
                    records.append({
                        "id": f"SQ{sequence:05d}",
                        "category": category,
                        "question": question,
                        "source": "synthetic",
                    })
                    sequence += 1
                    if len(generated) >= target:
                        break
                if len(generated) >= target:
                    break
            if len(generated) >= target:
                break
        if len(generated) != target:
            raise RuntimeError(f"{category} only generated {len(generated)} of {target} questions")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic customer-service questions.")
    parser.add_argument("--output", type=Path, default=Path("data/synthetic-user-questions.jsonl"))
    args = parser.parse_args()
    records = generate_questions()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "total": len(records),
        "categories": CATEGORY_TARGETS,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
