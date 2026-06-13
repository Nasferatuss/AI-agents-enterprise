"""Deep Research Agent (module #7): plan → research via Tool Gateway → cited report."""

from workbench_app_research.api import router
from workbench_app_research.research import ResearchReport, run_research

__all__ = ["ResearchReport", "research_router", "router", "run_research"]

research_router = router
