"""Guarded Computer-Use QA (module #8): legacy UI sandbox + scenario runner + bug report."""

from workbench_app_cua.api import router
from workbench_app_cua.runner import QAReport, run_qa
from workbench_app_cua.scenarios import SCENARIOS

__all__ = ["QAReport", "SCENARIOS", "router", "run_qa"]
