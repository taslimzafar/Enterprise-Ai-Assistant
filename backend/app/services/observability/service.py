import os
import threading
from typing import Optional, Dict, Any, List
from collections import deque
from datetime import datetime, timezone

from app.core.logging import logger
from app.services.evaluation.metrics import calculate_percentiles
from app.services.observability.traces import TraceModel, SpanModel
from app.services.observability.errors import ErrorCategory, ErrorRecord, categorize_error

def is_sensitive_key(k: str) -> bool:
    k_lower = k.lower()
    # Explicitly exempt token count metrics
    if any(metric in k_lower for metric in ["input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens"]):
        return False
    sensitive_words = ["password", "secret", "authorization", "api_key", "credentials", "jwt", "chain_of_thought", "thought"]
    if any(sens in k_lower for sens in sensitive_words):
        return True
    if k_lower in ("token", "access_token", "refresh_token", "auth_token"):
        return True
    return False


def sanitize_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact sensitive keys and strip internal chain-of-thought."""
    sanitized = {}
    for k, v in data.items():
        if is_sensitive_key(k):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_metadata(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_metadata(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized


class ObservabilityService:
    """Thread-safe in-memory observability and tracing store."""

    def __init__(self, max_traces: int = 1000, max_errors: int = 1000):
        self._lock = threading.Lock()
        self._traces: Dict[str, TraceModel] = {}
        self._trace_order: deque = deque(maxlen=max_traces)
        self._latencies: List[float] = []
        self._errors: deque = deque(maxlen=max_errors)
        self._request_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._tool_usage_counts: Dict[str, int] = {}
        self._workflow_execution_count = 0
        self._approval_wait_count = 0

        # Detect optional external tracing providers
        self.langsmith_enabled = os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
        self.otel_enabled = bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
        if self.langsmith_enabled:
            logger.info("LangSmith tracing is enabled via environment configuration.")
        if self.otel_enabled:
            logger.info("OpenTelemetry exporter is configured via environment.")

    def start_trace(
        self,
        name: str,
        organization_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TraceModel:
        trace = TraceModel(
            name=name,
            organization_id=organization_id,
            user_id=user_id,
            metadata=sanitize_metadata(metadata or {}),
        )
        with self._lock:
            self._traces[trace.trace_id] = trace
            self._trace_order.append(trace.trace_id)
            self._request_count += 1
        return trace

    def start_span(
        self,
        trace_id: str,
        name: str,
        component: str,
        parent_span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SpanModel:
        span = SpanModel(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            component=component,
            metadata=sanitize_metadata(metadata or {}),
        )
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace:
                trace.spans.append(span)
        return span

    def finish_span(
        self,
        span: SpanModel,
        status: str = "OK",
        error: Optional[str] = None,
    ) -> None:
        span.finish(status=status, error=error)
        if span.duration_ms is not None:
            with self._lock:
                self._latencies.append(span.duration_ms)

    def finish_trace(
        self,
        trace: TraceModel,
        status: str = "OK",
    ) -> None:
        trace.finish(status=status)
        if trace.total_duration_ms is not None:
            with self._lock:
                self._latencies.append(trace.total_duration_ms)

    def record_metric(
        self,
        organization_id: Optional[str] = None,
        latency_ms: Optional[float] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        tool_name: Optional[str] = None,
        is_workflow: bool = False,
        is_approval: bool = False,
        error: Optional[Exception] = None,
        component: str = "API",
    ) -> None:
        with self._lock:
            self._request_count += 1
            if latency_ms is not None:
                self._latencies.append(latency_ms)
            self._total_input_tokens += tokens_in
            self._total_output_tokens += tokens_out
            if tool_name:
                self._tool_usage_counts[tool_name] = self._tool_usage_counts.get(tool_name, 0) + 1
            if is_workflow:
                self._workflow_execution_count += 1
            if is_approval:
                self._approval_wait_count += 1
            if error:
                cat = categorize_error(error)
                self._errors.append(
                    ErrorRecord(
                        category=cat,
                        component=component,
                        message=str(error),
                        organization_id=organization_id,
                    )
                )

    def get_trace(self, trace_id: str, organization_id: Optional[str] = None) -> Optional[TraceModel]:
        with self._lock:
            trace = self._traces.get(trace_id)
            if not trace:
                return None
            if organization_id and trace.organization_id and trace.organization_id != organization_id:
                return None
            return trace

    def get_metrics(self, organization_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            # Latency calculations
            pct = calculate_percentiles(self._latencies)

            # Filter errors by org if given
            errors_list = [
                e for e in self._errors
                if not organization_id or not e.organization_id or e.organization_id == organization_id
            ]
            error_count = len(errors_list)
            error_rate = round(error_count / self._request_count, 4) if self._request_count > 0 else 0.0

            # Error category breakdown
            categories_count: Dict[str, int] = {}
            for e in errors_list:
                categories_count[e.category.value] = categories_count.get(e.category.value, 0) + 1

            total_tokens = self._total_input_tokens + self._total_output_tokens

            return {
                "request_count": self._request_count,
                "error_count": error_count,
                "error_rate": error_rate,
                "latency_summary": pct,
                "tokens": {
                    "input_tokens": self._total_input_tokens,
                    "output_tokens": self._total_output_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost": "unavailable",
                },
                "tool_usage": dict(self._tool_usage_counts),
                "workflow_executions": self._workflow_execution_count,
                "approval_waits": self._approval_wait_count,
                "error_categories": categories_count,
            }

    def clear(self) -> None:
        """Reset internal metrics for test isolation."""
        with self._lock:
            self._traces.clear()
            self._trace_order.clear()
            self._latencies.clear()
            self._errors.clear()
            self._request_count = 0
            self._total_input_tokens = 0
            self._total_output_tokens = 0
            self._tool_usage_counts.clear()
            self._workflow_execution_count = 0
            self._approval_wait_count = 0


observability_service = ObservabilityService()
