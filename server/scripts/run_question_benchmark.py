import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
from statistics import median
import sys
import time

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.agent.graph import SupportGraph
from app.agent.service import SupportAgent
from app.rag.retriever import KnowledgeBase


KNOWLEDGE_CATEGORIES = {
    "returns_policy", "products_warranty", "payment_invoice", "account_security", "membership", "unknown"
}


def percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentage))
    return round(ordered[index], 2)


def load_questions(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an offline benchmark over synthetic user questions.")
    parser.add_argument("--input", type=Path, default=Path("data/synthetic-user-questions.jsonl"))
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--output", type=Path, default=Path("reports/question-benchmark-1000.json"))
    args = parser.parse_args()

    records = load_questions(args.input)
    if args.sample_size > len(records):
        raise ValueError("sample size cannot exceed dataset size")
    sample = random.Random(args.seed).sample(records, args.sample_size)
    root = Path(__file__).resolve().parents[2]
    graph = SupportGraph(SupportAgent(KnowledgeBase(root / "knowledge-base")))

    intents: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    category_success: Counter[str] = Counter()
    latencies: list[float] = []
    failures: list[dict] = []
    retrieval_misses: Counter[str] = Counter()
    detected_unknowns: Counter[str] = Counter()
    tool_calls = 0
    handoffs = 0
    known_knowledge_questions = 0
    cited_known_questions = 0
    unknown_questions = 0
    detected_unknown_count = 0

    started = time.perf_counter()
    for index, record in enumerate(sample):
        item_started = time.perf_counter()
        category = record["category"]
        categories[category] += 1
        try:
            response = graph.respond(record["question"], "demo-user", f"benchmark-{index}")
            latency_ms = (time.perf_counter() - item_started) * 1000
            latencies.append(latency_ms)
            intents[response.intent] += 1
            tool_calls += int(bool(response.tool_calls))
            handoffs += int(response.needs_human)
            if response.answer.strip():
                category_success[category] += 1
            else:
                failures.append({"id": record["id"], "question": record["question"], "error": "empty answer"})
            knowledge_response = response.intent in {"knowledge_qa", "general_chat"} and not response.needs_human
            if category == "unknown" and knowledge_response:
                unknown_questions += 1
                if not response.citations:
                    detected_unknown_count += 1
                    detected_unknowns[record["question"]] += 1
            elif category in KNOWLEDGE_CATEGORIES and knowledge_response:
                known_knowledge_questions += 1
                if response.citations:
                    cited_known_questions += 1
                else:
                    retrieval_misses[record["question"]] += 1
        except Exception as exc:
            latencies.append((time.perf_counter() - item_started) * 1000)
            failures.append({"id": record["id"], "question": record["question"], "error": str(exc)})

    elapsed_seconds = time.perf_counter() - started
    report = {
        "dataset_size": len(records),
        "sample_size": len(sample),
        "seed": args.seed,
        "mode": "offline-no-deepseek-billing",
        "success_count": len(sample) - len(failures),
        "success_rate": round((len(sample) - len(failures)) / len(sample), 4),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "throughput_per_second": round(len(sample) / elapsed_seconds, 2),
        "latency_ms": {
            "median": round(median(latencies), 2),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies, default=0), 2),
        },
        "intent_distribution": dict(intents.most_common()),
        "category_distribution": dict(categories.most_common()),
        "category_success_rate": {
            category: round(category_success[category] / count, 4)
            for category, count in sorted(categories.items())
        },
        "tool_call_count": tool_calls,
        "handoff_count": handoffs,
        "known_knowledge_citation_rate": round(
            cited_known_questions / known_knowledge_questions, 4
        ) if known_knowledge_questions else 1.0,
        "unknown_gap_detection_rate": round(
            detected_unknown_count / unknown_questions, 4
        ) if unknown_questions else 1.0,
        "top_retrieval_misses": [
            {"question": question, "count": count} for question, count in retrieval_misses.most_common(20)
        ],
        "top_detected_unknown_questions": [
            {"question": question, "count": count} for question, count in detected_unknowns.most_common(20)
        ],
        "failures": failures[:50],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(
        "\n".join([
            "# 1000 条用户提问离线测试报告",
            "",
            f"- 数据集：{report['dataset_size']} 条合成用户提问",
            f"- 本次抽样：{report['sample_size']} 条（seed={report['seed']}）",
            f"- 成功处理：{report['success_count']} 条（{report['success_rate'] * 100:.2f}%）",
            f"- 总耗时：{report['elapsed_seconds']} 秒",
            f"- 吞吐量：{report['throughput_per_second']} 条/秒",
            f"- 延迟：中位数 {report['latency_ms']['median']} ms，P95 {report['latency_ms']['p95']} ms",
            f"- 工具调用：{report['tool_call_count']} 次",
            f"- 转人工：{report['handoff_count']} 次",
            f"- 已知知识引用率：{report['known_knowledge_citation_rate'] * 100:.2f}%",
            f"- 未知领域识别率：{report['unknown_gap_detection_rate'] * 100:.2f}%",
            "",
            "## 意图分布",
            "",
            *[f"- {name}: {count}" for name, count in report["intent_distribution"].items()],
            "",
            "## 已有知识的检索遗漏",
            "",
            *(
                [f"- {item['question']} ({item['count']} 次)" for item in report["top_retrieval_misses"]]
                or ["- 暂未检测到检索遗漏"]
            ),
            "",
            "## 检测到的未知领域问题",
            "",
            *(
                [f"- {item['question']} ({item['count']} 次)" for item in report["top_detected_unknown_questions"]]
                or ["- 暂未检测到未知领域问题"]
            ),
        ]),
        encoding="utf-8",
    )
    print(json.dumps({"json_report": str(args.output), "markdown_report": str(markdown_path), **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
