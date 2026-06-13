"""A small in-process research corpus for the sample connectors.

Self-contained and deterministic — no live internet (which would also be a real
SSRF/safety surface). A production gateway would register connectors that hit
real MCP servers / search APIs behind the same boundary.
"""

CORPUS: dict[str, dict[str, str]] = {
    "https://docs.local/rag": {
        "title": "Retrieval-Augmented Generation",
        "text": "Retrieval-augmented generation (RAG) grounds a language model in "
        "external documents. An ingestion pipeline chunks documents and stores "
        "embeddings in a vector database; at query time the most relevant chunks "
        "are retrieved and added to the prompt. Hybrid search combines dense "
        "vector similarity with lexical BM25 for better recall. Quality is "
        "measured with retrieval hit rate, context precision, and faithfulness.",
    },
    "https://docs.local/agents": {
        "title": "Building Effective Agents",
        "text": "An agent is a language model in a loop with tools. Each turn the "
        "model may call a tool; the result is fed back and the loop continues "
        "until the model answers. Predictable workflows with explicit steps and "
        "approval gates are preferred over fully autonomous agents when the cost "
        "of error is high. Tool use should go through a gateway with an allowlist "
        "and an audit log.",
    },
    "https://docs.local/observability": {
        "title": "Agent Observability",
        "text": "Observability for agents captures a trace of every run: steps, "
        "tool calls, model calls, token usage, latency, cost, and errors. A "
        "failure taxonomy groups non-successful runs. A minimal custom trace "
        "schema is usually enough; a full third-party clone is rarely worth it.",
    },
    "https://docs.local/evals": {
        "title": "Evaluating LLM Systems",
        "text": "Evaluation turns 'it seems to work' into measured quality. RAG "
        "evals score retrieval hit rate, citation accuracy, and answer "
        "faithfulness, often with an LLM judge that must be stronger than the "
        "model under test. Synthetic question-answer datasets bootstrap coverage. "
        "Regression gates stop quality from silently dropping.",
    },
    "https://docs.local/routing": {
        "title": "Cost-Aware Model Routing",
        "text": "A model router sends each task to the cheapest model that can "
        "handle it: local models for simple tasks, cheap APIs for standard work, "
        "frontier models for hard reasoning and judging. Fallback across providers "
        "improves reliability. Per-call cost and latency telemetry guides tuning.",
    },
    "https://docs.local/governance": {
        "title": "AI Governance & Guardrails",
        "text": "Governance for agentic systems means real controls: read-only "
        "data access with allowlists, PII detection, human approval gates before "
        "risky actions, and an audit log of tool calls. Connectivity through MCP "
        "increases the security surface, so the boundary must be in the gateway.",
    },
}
