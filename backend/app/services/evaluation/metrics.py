import math
import re
from typing import List, Dict, Any, Optional, Set


def _tokenize(text: str) -> Set[str]:
    """Tokenize string into lowercase alphanumeric words."""
    if not text:
        return set()
    return set(re.findall(r"\b\w+\b", text.lower()))


def compute_retrieval_metrics(
    retrieved_sources: List[str],
    expected_sources: List[str]
) -> Dict[str, float]:
    """
    Compute deterministic retrieval metrics: precision, recall, and F1.
    """
    ret_set = set(retrieved_sources or [])
    exp_set = set(expected_sources or [])

    if not exp_set:
        # If no sources were expected, retrieval is perfect if none retrieved, or 0.0 if unneeded sources retrieved
        recall = 1.0
        precision = 1.0 if not ret_set else 0.8
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        return {"precision": precision, "recall": recall, "f1": f1}

    if not ret_set:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    intersection = ret_set.intersection(exp_set)
    precision = len(intersection) / len(ret_set)
    recall = len(intersection) / len(exp_set)
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def compute_groundedness(
    answer: str,
    retrieved_contexts: List[str]
) -> float:
    """
    Compute groundedness score between 0.0 and 1.0 based on lexical overlap
    between answer claims and retrieved contexts.
    """
    if not answer:
        return 0.0

    ans_tokens = _tokenize(answer)
    # Stop words / common tokens to exclude from groundedness ratio
    stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were", "it", "this", "that"}
    meaningful_tokens = ans_tokens - stopwords

    if not meaningful_tokens:
        return 1.0

    if not retrieved_contexts:
        # Check if the answer is explicitly declining to answer due to missing context
        no_ans_signals = ["do not have", "cannot find", "no information", "not found", "does not contain", "no access"]
        ans_lower = answer.lower()
        if any(sig in ans_lower for sig in no_ans_signals):
            return 1.0
        return 0.0

    context_tokens = set()
    for ctx in retrieved_contexts:
        context_tokens.update(_tokenize(ctx))

    supported = meaningful_tokens.intersection(context_tokens)
    score = len(supported) / len(meaningful_tokens)
    return round(min(1.0, max(0.0, score)), 4)


def compute_correctness(
    actual_answer: str,
    expected_answer: Optional[str],
    required_keywords: Optional[List[str]] = None
) -> float:
    """
    Evaluate answer correctness using keyword matching and token overlap.
    """
    if not actual_answer:
        return 0.0

    actual_lower = actual_answer.lower()

    keyword_score = 1.0
    if required_keywords:
        matched = sum(1 for kw in required_keywords if kw.lower() in actual_lower)
        keyword_score = matched / len(required_keywords)

    if not expected_answer:
        return round(keyword_score, 4)

    act_tokens = _tokenize(actual_answer)
    exp_tokens = _tokenize(expected_answer)

    if not exp_tokens:
        return round(keyword_score, 4)

    intersection = act_tokens.intersection(exp_tokens)
    union = act_tokens.union(exp_tokens)
    jaccard = len(intersection) / len(union) if union else 1.0

    # Weighted combination: 60% keywords (if any), 40% jaccard overlap
    if required_keywords:
        final_score = (0.6 * keyword_score) + (0.4 * jaccard)
    else:
        final_score = jaccard

    return round(min(1.0, max(0.0, final_score)), 4)


def compute_citation_metrics(
    answer: str,
    retrieved_sources: List[str]
) -> Dict[str, float]:
    """
    Measure citation correctness and completeness.
    """
    if not answer:
        return {"correctness": 0.0, "completeness": 0.0}

    ans_lower = answer.lower()
    cited = [s for s in (retrieved_sources or []) if s.lower() in ans_lower]

    # Completeness: fraction of retrieved sources referenced
    completeness = len(cited) / len(retrieved_sources) if retrieved_sources else 1.0

    # Correctness: 1.0 if citations refer to actual retrieved sources
    correctness = 1.0 if not retrieved_sources or len(cited) > 0 else 0.5

    return {
        "correctness": round(correctness, 4),
        "completeness": round(completeness, 4),
    }


def compute_no_answer_correctness(actual_answer: str) -> float:
    """
    Determine whether an answer correctly refused to hallucinate when context was missing.
    """
    if not actual_answer:
        return 0.0

    signals = [
        "do not have",
        "cannot find",
        "no information",
        "not available",
        "not found",
        "does not contain",
        "no access",
        "unable to find",
        "not mentioned",
        "no record",
    ]
    ans_lower = actual_answer.lower()
    matched = any(s in ans_lower for s in signals)
    return 1.0 if matched else 0.0


def calculate_percentiles(latencies: List[float]) -> Dict[str, float]:
    """
    Calculate statistical latency percentiles: p50, p95, p99, average, min, max.
    """
    if not latencies:
        return {
            "count": 0,
            "average_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
        }

    sorted_lat = sorted(latencies)
    n = len(sorted_lat)

    def _percentile(p: float) -> float:
        idx = int(math.ceil((p / 100.0) * n)) - 1
        idx = max(0, min(n - 1, idx))
        return sorted_lat[idx]

    return {
        "count": n,
        "average_ms": round(sum(sorted_lat) / n, 2),
        "p50_ms": round(_percentile(50.0), 2),
        "p95_ms": round(_percentile(95.0), 2),
        "p99_ms": round(_percentile(99.0), 2),
        "min_ms": round(sorted_lat[0], 2),
        "max_ms": round(sorted_lat[-1], 2),
    }
