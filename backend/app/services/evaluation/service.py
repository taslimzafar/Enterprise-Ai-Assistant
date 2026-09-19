from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.db.models.evaluation import EvaluationRun, EvaluationRecord
from app.services.evaluation.datasets import list_datasets, get_dataset
from app.services.evaluation.metrics import calculate_percentiles
from app.services.evaluation.runner import EvaluationRunner
from app.services.evaluation.schemas import (
    EvaluationRunRequest,
    EvaluationRunResponse,
    EvaluationRecordResponse,
    EvaluationMetricsResponse,
    CategoryMetric,
    LatencyPercentiles,
    EvaluationDatasetSchema,
)


class EvaluationService:
    """Service layer managing evaluation runs, persistence, and aggregations."""

    async def run_evaluation(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: Optional[str],
        request: EvaluationRunRequest,
    ) -> EvaluationRun:
        return await EvaluationRunner.run_evaluation(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            categories=request.categories,
        )

    async def list_runs(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[EvaluationRun], int]:
        count_query = select(func.count()).select_from(EvaluationRun).filter(
            EvaluationRun.organization_id == organization_id
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        query = (
            select(EvaluationRun)
            .filter(EvaluationRun.organization_id == organization_id)
            .order_by(desc(EvaluationRun.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(query)
        return list(result.scalars().all()), total

    async def get_run_details(
        self,
        db: AsyncSession,
        organization_id: str,
        run_id: str,
    ) -> Optional[EvaluationRun]:
        query = (
            select(EvaluationRun)
            .options(selectinload(EvaluationRun.records))
            .filter(
                EvaluationRun.id == run_id,
                EvaluationRun.organization_id == organization_id,
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_metrics(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> EvaluationMetricsResponse:
        # Fetch all records for the organization
        query = select(EvaluationRecord).filter(
            EvaluationRecord.organization_id == organization_id
        )
        result = await db.execute(query)
        records = list(result.scalars().all())

        # Count total runs
        runs_query = select(func.count()).select_from(EvaluationRun).filter(
            EvaluationRun.organization_id == organization_id
        )
        runs_count = (await db.execute(runs_query)).scalar_one()

        if not records:
            empty_latency = LatencyPercentiles(
                count=0,
                average_ms=0.0,
                p50_ms=0.0,
                p95_ms=0.0,
                p99_ms=0.0,
                min_ms=0.0,
                max_ms=0.0,
            )
            return EvaluationMetricsResponse(
                total_runs=runs_count,
                total_evaluations=0,
                pass_rate=0.0,
                average_correctness=0.0,
                average_groundedness=0.0,
                average_retrieval_score=0.0,
                categories=[],
                latency=empty_latency,
            )

        total_cases = len(records)
        passed_cases = sum(1 for r in records if r.status == "PASSED")
        pass_rate = round(passed_cases / total_cases, 4)

        avg_correctness = round(sum(r.correctness_score for r in records) / total_cases, 4)
        avg_groundedness = round(sum(r.groundedness_score for r in records) / total_cases, 4)
        avg_retrieval = round(sum(r.retrieval_score for r in records) / total_cases, 4)

        # Categorical grouping
        categories_dict: Dict[str, List[EvaluationRecord]] = {}
        for r in records:
            cat = r.category or "unknown"
            categories_dict.setdefault(cat, []).append(r)

        category_metrics: List[CategoryMetric] = []
        for cat, cat_records in categories_dict.items():
            c_total = len(cat_records)
            c_passed = sum(1 for cr in cat_records if cr.status == "PASSED")
            category_metrics.append(
                CategoryMetric(
                    category=cat,
                    total_cases=c_total,
                    passed_cases=c_passed,
                    pass_rate=round(c_passed / c_total, 4) if c_total > 0 else 0.0,
                    average_correctness=round(sum(cr.correctness_score for cr in cat_records) / c_total, 4),
                    average_groundedness=round(sum(cr.groundedness_score for cr in cat_records) / c_total, 4),
                    average_retrieval=round(sum(cr.retrieval_score for cr in cat_records) / c_total, 4),
                )
            )

        latencies = [r.latency_ms for r in records if r.latency_ms is not None]
        pct = calculate_percentiles(latencies)
        latency_summary = LatencyPercentiles(**pct)

        return EvaluationMetricsResponse(
            total_runs=runs_count,
            total_evaluations=total_cases,
            pass_rate=pass_rate,
            average_correctness=avg_correctness,
            average_groundedness=avg_groundedness,
            average_retrieval_score=avg_retrieval,
            categories=category_metrics,
            latency=latency_summary,
        )

    def list_datasets(self) -> List[EvaluationDatasetSchema]:
        return list_datasets()

    def get_dataset(self, dataset_id: str, version: Optional[str] = None) -> Optional[EvaluationDatasetSchema]:
        return get_dataset(dataset_id, version)


evaluation_service = EvaluationService()
