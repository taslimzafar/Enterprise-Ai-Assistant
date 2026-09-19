from typing import Dict, Any, List, Optional
from app.services.evaluation.metrics import (
    compute_retrieval_metrics,
    compute_groundedness,
    compute_correctness,
    compute_citation_metrics,
    compute_no_answer_correctness,
)
from app.services.evaluation.schemas import TestCaseSchema


class RAGEvaluator:
    """Evaluates RAG pipeline responses against expected ground truth."""

    @staticmethod
    def evaluate(
        test_case: TestCaseSchema,
        actual_answer: str,
        retrieved_source_ids: List[str],
        retrieved_contexts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        ret_metrics = compute_retrieval_metrics(
            retrieved_sources=retrieved_source_ids,
            expected_sources=test_case.expected_source_ids,
        )
        groundedness = compute_groundedness(
            answer=actual_answer,
            retrieved_contexts=retrieved_contexts or [],
        )
        required_keywords = test_case.metadata.get("required_keywords")
        correctness = compute_correctness(
            actual_answer=actual_answer,
            expected_answer=test_case.expected_answer,
            required_keywords=required_keywords,
        )
        citation = compute_citation_metrics(
            answer=actual_answer,
            retrieved_sources=retrieved_source_ids,
        )

        passed = (
            ret_metrics["recall"] >= 0.8
            and correctness >= 0.5
            and groundedness >= 0.5
        ) if test_case.expected_source_ids else (correctness >= 0.5)

        return {
            "passed": passed,
            "retrieval_score": ret_metrics["recall"],
            "precision": ret_metrics["precision"],
            "recall": ret_metrics["recall"],
            "f1": ret_metrics["f1"],
            "groundedness_score": groundedness,
            "correctness_score": correctness,
            "citation_metrics": citation,
        }


class NoAnswerEvaluator:
    """Evaluates correct refusal to answer when facts are absent."""

    @staticmethod
    def evaluate(test_case: TestCaseSchema, actual_answer: str) -> Dict[str, Any]:
        no_ans_score = compute_no_answer_correctness(actual_answer)
        groundedness = 1.0 if no_ans_score == 1.0 else 0.0
        passed = no_ans_score == 1.0
        return {
            "passed": passed,
            "correctness_score": no_ans_score,
            "groundedness_score": groundedness,
            "retrieval_score": 1.0,
        }


class AgentEvaluator:
    """Evaluates intent classification and tool routing behavior."""

    @staticmethod
    def evaluate(
        test_case: TestCaseSchema,
        classified_intent: str,
        selected_tool: Optional[str] = None,
        actual_answer: Optional[str] = None,
    ) -> Dict[str, Any]:
        expected_intent = test_case.metadata.get("expected_intent")
        expected_tool = test_case.metadata.get("expected_tool")

        intent_correct = (
            classified_intent.upper() == expected_intent.upper()
            if expected_intent else True
        )
        tool_correct = (
            selected_tool == expected_tool
            if expected_tool else (selected_tool is None)
        )

        passed = intent_correct and tool_correct
        score = 1.0 if passed else (0.5 if (intent_correct or tool_correct) else 0.0)

        return {
            "passed": passed,
            "correctness_score": score,
            "groundedness_score": 1.0 if passed else 0.0,
            "retrieval_score": 1.0,
            "intent_correct": intent_correct,
            "tool_correct": tool_correct,
        }


class ToolEvaluator:
    """Evaluates Phase 9 tool execution results, validation, and error states."""

    @staticmethod
    def evaluate(
        tool_name: str,
        execution_status: str,  # 'SUCCESS', 'VALIDATION_ERROR', 'PERMISSION_DENIED', 'UNKNOWN_TOOL'
        result: Any,
        expected_result: Any = None,
    ) -> Dict[str, Any]:
        passed = False
        score = 0.0

        if execution_status == "SUCCESS":
            if expected_result is not None:
                passed = str(result) == str(expected_result)
                score = 1.0 if passed else 0.5
            else:
                passed = True
                score = 1.0
        elif execution_status in ("VALIDATION_ERROR", "PERMISSION_DENIED", "UNKNOWN_TOOL"):
            # Expected error handling
            passed = True
            score = 1.0

        return {
            "passed": passed,
            "correctness_score": score,
            "groundedness_score": 1.0,
            "retrieval_score": 1.0,
            "execution_status": execution_status,
        }


class WorkflowEvaluator:
    """Evaluates workflow execution completion, step success, and retries."""

    @staticmethod
    def evaluate(
        execution_status: str,
        total_steps: int,
        executed_steps: int,
        failed_steps: int,
        retry_count: int,
        duration_ms: float,
    ) -> Dict[str, Any]:
        passed = execution_status == "COMPLETED" and failed_steps == 0
        step_success_rate = (
            (executed_steps - failed_steps) / executed_steps
            if executed_steps > 0 else 0.0
        )
        score = 1.0 if passed else round(step_success_rate * 0.8, 2)

        return {
            "passed": passed,
            "correctness_score": score,
            "groundedness_score": 1.0,
            "retrieval_score": 1.0,
            "step_success_rate": round(step_success_rate, 4),
            "retry_count": retry_count,
            "duration_ms": duration_ms,
        }


class SecurityEvaluator:
    """Evaluates prompt injection rejection, cross-tenant denial, and unauthorized actions."""

    @staticmethod
    def evaluate(
        test_case: TestCaseSchema,
        actual_response: str,
        was_rejected: bool,
    ) -> Dict[str, Any]:
        should_reject = test_case.metadata.get("should_reject", True)
        passed = was_rejected == should_reject
        score = 1.0 if passed else 0.0

        return {
            "passed": passed,
            "correctness_score": score,
            "groundedness_score": 1.0,
            "retrieval_score": 1.0,
            "rejection_enforced": was_rejected,
        }
