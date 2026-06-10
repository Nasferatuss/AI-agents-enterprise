"""Evaluation Engine endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from workbench_evals import EvalDataset, EvalReport, generate_dataset, run_rag_eval
from workbench_evals.synthetic import SyntheticGenerationError
from workbench_gateway.routes import rag as rag_routes
from workbench_rag.embeddings import EmbeddingError
from workbench_runtime import get_router
from workbench_runtime.router import NoProviderAvailableError

router = APIRouter(prefix="/v1/evals", tags=["evals"])


class SyntheticSpec(BaseModel):
    n: int = Field(default=10, ge=1, le=100)


class RagEvalRequest(BaseModel):
    index: str
    top_k: int = Field(default=5, ge=1, le=50)
    judge: bool = True
    dataset: EvalDataset | None = None
    synthetic: SyntheticSpec | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "RagEvalRequest":
        if (self.dataset is None) == (self.synthetic is None):
            raise ValueError("provide exactly one of `dataset` or `synthetic`")
        return self


@router.post("/rag", response_model=EvalReport)
async def run_rag(req: RagEvalRequest) -> EvalReport:
    pipeline = rag_routes.get_pipeline(req.index)
    if not await pipeline.store.exists():
        raise HTTPException(status_code=404, detail=f"unknown index: {req.index}")
    model_router = get_router()
    try:
        dataset = req.dataset or await generate_dataset(
            pipeline, model_router, name=f"synthetic-{req.index}", n=req.synthetic.n
        )
        return await run_rag_eval(pipeline, model_router, dataset, top_k=req.top_k, judge=req.judge)
    except (NoProviderAvailableError, EmbeddingError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SyntheticGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
