"""RAG eval runner: dataset → per-example metrics → aggregated, persisted report."""

import datetime
from pathlib import Path

from workbench_evals.answerer import _render_context, rag_answer
from workbench_evals.judge import judge_faithfulness, judge_relevance
from workbench_evals.metrics import citation_metrics, retrieval_metrics
from workbench_evals.types import (
    EvalAggregates,
    EvalDataset,
    EvalReport,
    ExampleReport,
)
from workbench_rag.pipeline import RagPipeline
from workbench_runtime.router import ModelRouter
from workbench_shared.config import get_settings
from workbench_shared.logging import get_logger

log = get_logger(__name__)


def _add_cost(total: float | None, part: float | None) -> float | None:
    return None if (total is None or part is None) else total + part


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


async def run_rag_eval(
    pipeline: RagPipeline,
    router: ModelRouter,
    dataset: EvalDataset,
    top_k: int = 5,
    judge: bool = True,
    save: bool = True,
) -> EvalReport:
    examples: list[ExampleReport] = []
    cost: float | None = 0.0

    for ex in dataset.examples:
        answer, retrieved, answer_cost = await rag_answer(pipeline, router, ex.question, top_k)
        cost = _add_cost(cost, answer_cost)
        report = ExampleReport(
            example_id=ex.id,
            question=ex.question,
            retrieval=retrieval_metrics(retrieved, ex.relevant_sources),
            retrieved=retrieved,
            answer=answer,
            citations=citation_metrics(answer, len(retrieved)),
        )
        if judge:
            context = _render_context(retrieved)
            report.faithfulness, judge_cost = await judge_faithfulness(
                router, ex.question, context, answer
            )
            cost = _add_cost(cost, judge_cost)
            report.answer_relevance, judge_cost = await judge_relevance(router, ex.question, answer)
            cost = _add_cost(cost, judge_cost)
        examples.append(report)

    aggregates = EvalAggregates(
        n=len(examples),
        hit_rate=_mean([1.0 if e.retrieval.hit else 0.0 for e in examples]),
        mrr=_mean([e.retrieval.reciprocal_rank for e in examples]),
        context_precision=_mean([e.retrieval.context_precision for e in examples]),
        citation_accuracy=_mean([e.citations.accuracy for e in examples if e.citations]),
        faithfulness=_mean([e.faithfulness.score for e in examples if e.faithfulness])
        if judge
        else None,
        answer_relevance=_mean([e.answer_relevance.score for e in examples if e.answer_relevance])
        if judge
        else None,
    )
    report = EvalReport(
        dataset=dataset.name,
        index=pipeline.store.collection,
        top_k=top_k,
        judged=judge,
        created_at=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        aggregates=aggregates,
        examples=examples,
        llm_cost_usd=cost,
    )
    if save:
        report.report_path = _save(report)
    log.info(
        "rag eval finished",
        dataset=dataset.name,
        index=report.index,
        n=aggregates.n,
        hit_rate=round(aggregates.hit_rate, 3),
        mrr=round(aggregates.mrr, 3),
        faithfulness=aggregates.faithfulness,
        cost_usd=cost,
        report=report.report_path,
    )
    return report


def _save(report: EvalReport) -> str:
    results_dir = Path(get_settings().eval_results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.created_at.replace(":", "-").replace("+00-00", "Z")
    path = results_dir / f"{stamp}_{report.dataset}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return str(path)
