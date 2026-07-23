"""Run the deterministic AI/RAG offline regression suite.

This suite does not call a model provider and is safe for CI. It measures the
local guarantees that must remain available during provider outages: reviewed
source retrieval, refusal, risk classification, memory retention and PII
redaction.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "offline-eval-only")
os.environ.setdefault("DEEPSEEK_API_KEY", "")

from backend.services.conversation_memory import compress_history  # noqa: E402
from backend.services.rag import _anonymize, answer_with_knowledge, retrieve  # noqa: E402
from backend.services.risk_engine import assess_risk  # noqa: E402
from database.database import Base  # noqa: E402
from database.models import KnowledgeDocument  # noqa: E402

LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def evaluate_case(db: Session, case: dict) -> tuple[bool, dict]:
    kind = case["kind"]
    if kind == "retrieval":
        chunks = retrieve(db, case["query"])
        titles = [chunk.title for chunk in chunks]
        return bool(titles and titles[0] == case["expected_title"]), {"retrieved_titles": titles}
    if kind == "excluded_source":
        titles = [chunk.title for chunk in retrieve(db, case["query"])]
        return case["forbidden_title"] not in titles, {"retrieved_titles": titles}
    if kind == "refusal":
        answer = asyncio.run(answer_with_knowledge(db, case["query"]))
        return answer.refusal_reason == case["expected_reason"], {"refusal_reason": answer.refusal_reason}
    if kind == "risk":
        result = assess_risk(case["text"])
        passed = True
        if "minimum_level" in case:
            passed = passed and LEVELS[result.level] >= LEVELS[case["minimum_level"]]
        if "maximum_level" in case:
            passed = passed and LEVELS[result.level] <= LEVELS[case["maximum_level"]]
        return passed, {"level": result.level, "score": result.score, "signals": list(result.signals)}
    if kind == "memory":
        summary = compress_history(case["messages"], max_chars=case["max_chars"])
        passed = len(summary) <= case["max_chars"] and all(term in summary for term in case["required_terms"])
        return passed, {"summary": summary, "length": len(summary)}
    if kind == "privacy":
        redacted = _anonymize(case["text"])
        passed = all(term not in redacted for term in case["forbidden_terms"])
        return passed, {"redacted": redacted}
    raise ValueError(f"Unsupported evaluation kind: {kind}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results") / "latest.json")
    args = parser.parse_args()

    dataset = json.loads(args.cases.read_text(encoding="utf-8"))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    results: list[dict] = []
    with Session(engine) as db:
        db.add_all(KnowledgeDocument(**document) for document in dataset["corpus"])
        db.commit()
        for case in dataset["cases"]:
            passed, details = evaluate_case(db, case)
            results.append({"id": case["id"], "kind": case["kind"], "passed": passed, "details": details})

    counts = Counter(item["kind"] for item in results)
    passed_counts = Counter(item["kind"] for item in results if item["passed"])
    overall = sum(item["passed"] for item in results) / len(results)
    risk_cases = [
        item for item in results
        if item["kind"] == "risk" and any(label in item["id"] for label in ("critical", "high"))
    ]
    privacy_cases = [item for item in results if item["kind"] == "privacy"]
    metrics = {
        "overall_accuracy": round(overall, 4),
        "risk_recall": round(sum(item["passed"] for item in risk_cases) / max(1, len(risk_cases)), 4),
        "privacy_pass_rate": round(sum(item["passed"] for item in privacy_cases) / max(1, len(privacy_cases)), 4),
        "by_kind": {kind: {"passed": passed_counts[kind], "total": total} for kind, total in sorted(counts.items())},
    }
    gates = dataset["quality_gates"]
    gates_passed = all(metrics[name] >= threshold for name, threshold in gates.items())
    report = {
        "dataset_version": dataset["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider_calls": 0,
        "metrics": metrics,
        "quality_gates": gates,
        "quality_gates_passed": gates_passed,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
