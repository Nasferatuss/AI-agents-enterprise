import json

import httpx
import pytest

from workbench_app_process.analyzer import (
    ProcessAnalysisError,
    ProcessStep,
    analyze_document,
    to_mermaid,
)
from workbench_runtime.providers import Provider
from workbench_runtime.router import ModelRouter


def test_mermaid_renders_nodes_and_edges():
    steps = [
        ProcessStep(id=1, actor="HR", action="create record", next=[2]),
        ProcessStep(id=2, actor="IT", action="provision laptop", next=[3]),
        ProcessStep(id=3, actor="Manager", action="approve access", next=[]),
    ]
    mermaid = to_mermaid(steps)
    assert mermaid.startswith("flowchart TD")
    assert 's1["HR: create record"]' in mermaid
    assert "s1 --> s2" in mermaid
    assert "s2 --> s3" in mermaid
    assert "s3 -->" not in mermaid  # terminal step has no outgoing edge


def test_mermaid_implicit_sequential_edges_when_next_missing():
    steps = [ProcessStep(id=1, action="a"), ProcessStep(id=2, action="b")]
    assert "s1 --> s2" in to_mermaid(steps)


def test_mermaid_escapes_quotes():
    steps = [ProcessStep(id=1, action='say "hi"')]
    assert "say 'hi'" in to_mermaid(steps)


def test_empty_steps():
    assert "No steps" in to_mermaid([])


def _router(text: str) -> ModelRouter:
    payload = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20},
    }
    handler = lambda request: httpx.Response(200, json=payload)  # noqa: E731
    provider = Provider(
        name="fake",
        kind="openai_compatible",
        base_url="http://fake/v1",
        api_key_env="",
        models={"default": "fake-model"},
    )
    router = ModelRouter(
        registry={"fake": provider},
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router.chain = lambda complexity: [("fake", "default")]  # type: ignore[method-assign]
    return router


async def test_analyze_document_builds_report_and_mermaid():
    analysis = {
        "entities": [{"name": "HR", "type": "actor"}, {"name": "HR System", "type": "system"}],
        "steps": [
            {"id": 1, "actor": "HR", "action": "create record", "next": [2]},
            {"id": 2, "actor": "IT", "action": "provision laptop", "next": []},
        ],
        "contradictions": ["contractors may never access production, but step grants it"],
        "backlog": [{"title": "Clarify contractor access", "priority": "high"}],
    }
    report = await analyze_document(_router(json.dumps(analysis)), "some spec document")

    assert len(report.entities) == 2
    assert len(report.steps) == 2
    assert report.contradictions[0].startswith("contractors")
    assert report.backlog[0].priority == "high"
    assert "s1 --> s2" in report.mermaid
    assert report.provider == "fake"


async def test_analyze_rejects_empty_document():
    with pytest.raises(ProcessAnalysisError):
        await analyze_document(_router("{}"), "   ")


async def test_analyze_rejects_non_json():
    with pytest.raises(ProcessAnalysisError):
        await analyze_document(_router("I cannot do that"), "doc")
