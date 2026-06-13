"""Evaluation Engine: datasets, retrieval metrics, LLM judges, eval reports."""

from workbench_evals.generator import SyntheticDataset, generate_eval_dataset
from workbench_evals.runner import run_rag_eval
from workbench_evals.synthetic import generate_dataset
from workbench_evals.types import EvalDataset, EvalReport, QAExample

__all__ = [
    "EvalDataset",
    "EvalReport",
    "QAExample",
    "SyntheticDataset",
    "generate_dataset",
    "generate_eval_dataset",
    "run_rag_eval",
]
