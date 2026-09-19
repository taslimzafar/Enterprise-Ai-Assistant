"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { 
  CheckSquare, 
  Play, 
  RefreshCw, 
  AlertCircle, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  BarChart3, 
  ChevronDown, 
  ChevronUp, 
  ShieldAlert,
  Layers,
  Sparkles
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';

interface EvaluationMetrics {
  total_runs: number;
  total_evaluations: number;
  pass_rate: number;
  average_correctness: number;
  average_groundedness: number;
  average_retrieval_score: number;
  categories: Array<{
    category: string;
    total_cases: number;
    passed_cases: number;
    pass_rate: number;
    average_correctness: number;
    average_groundedness: number;
    average_retrieval: number;
  }>;
  latency: {
    count: number;
    average_ms: number;
    p50_ms: number;
    p95_ms: number;
    p99_ms: number;
    min_ms: number;
    max_ms: number;
  };
}

interface EvaluationRecord {
  id: string;
  case_id: string;
  category: string;
  query: string;
  expected_answer?: string;
  actual_answer?: string;
  correctness_score: number;
  groundedness_score: number;
  retrieval_score: number;
  latency_ms: number;
  status: string;
  error?: string;
}

interface EvaluationRun {
  id: string;
  dataset_id: string;
  dataset_version: string;
  status: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  average_correctness: number;
  average_groundedness: number;
  average_retrieval_score: number;
  total_duration_ms: number;
  total_tokens: number;
  created_at: string;
  records?: EvaluationRecord[];
}

export default function EvaluationsPage() {
  const { activeOrganization } = useAuth();
  const [metrics, setMetrics] = useState<EvaluationMetrics | null>(null);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<EvaluationRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningEval, setRunningEval] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!activeOrganization) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const [metricsRes, runsRes] = await Promise.all([
        api.get(`/evaluations/metrics?org_id=${activeOrganization.id}`),
        api.get(`/evaluations?org_id=${activeOrganization.id}`),
      ]);
      setMetrics(metricsRes.data);
      setRuns(runsRes.data);
      if (runsRes.data.length > 0 && !selectedRun) {
        // Fetch details of latest run
        const detailRes = await api.get(`/evaluations/${runsRes.data[0].id}?org_id=${activeOrganization.id}`);
        setSelectedRun(detailRes.data);
      }
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || 'Failed to load evaluation data');
    } finally {
      setLoading(false);
    }
  }, [activeOrganization, selectedRun]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRunEvaluation = async () => {
    if (!activeOrganization) return;
    setRunningEval(true);
    setErrorMessage(null);
    try {
      const res = await api.post(`/evaluations/run?org_id=${activeOrganization.id}`, {
        dataset_id: "baseline_v1",
        dataset_version: "1.0.0",
      });
      setSelectedRun(res.data);
      await fetchData();
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || 'Evaluation run failed');
    } finally {
      setRunningEval(false);
    }
  };

  const handleSelectRun = async (runId: string) => {
    if (!activeOrganization) return;
    try {
      const res = await api.get(`/evaluations/${runId}?org_id=${activeOrganization.id}`);
      setSelectedRun(res.data);
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || 'Failed to fetch run details');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <CheckSquare className="w-6 h-6 text-indigo-600" />
            AI Evaluation Framework
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Deterministic quality, groundedness, retrieval, and regression benchmarks
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchData}
            disabled={loading}
            className="inline-flex items-center px-3 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={handleRunEvaluation}
            disabled={runningEval || !activeOrganization}
            className="inline-flex items-center px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 shadow-sm transition disabled:opacity-50"
          >
            <Play className={`w-4 h-4 mr-2 ${runningEval ? 'animate-spin' : ''}`} />
            {runningEval ? 'Evaluating...' : 'Run Evaluation (v1.0.0)'}
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md flex items-center gap-3 text-red-700">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <p className="text-sm">{errorMessage}</p>
        </div>
      )}

      {/* Summary Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Pass Rate</span>
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? `${(metrics.pass_rate * 100).toFixed(1)}%` : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">
            {metrics ? `${metrics.total_evaluations} test cases evaluated` : 'No data'}
          </span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Correctness</span>
            <Sparkles className="w-5 h-5 text-indigo-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? `${(metrics.average_correctness * 100).toFixed(1)}%` : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">Semantic & lexical match</span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Groundedness</span>
            <Layers className="w-5 h-5 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? `${(metrics.average_groundedness * 100).toFixed(1)}%` : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">Context claim attribution</span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Retrieval Recall</span>
            <BarChart3 className="w-5 h-5 text-purple-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? `${(metrics.average_retrieval_score * 100).toFixed(1)}%` : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">Source chunk discovery</span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">p50 Latency</span>
            <Clock className="w-5 h-5 text-amber-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics?.latency ? `${metrics.latency.p50_ms.toFixed(0)} ms` : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">
            p95: {metrics?.latency ? `${metrics.latency.p95_ms.toFixed(0)} ms` : '--'}
          </span>
        </div>
      </div>

      {/* Main Content: Runs List & Detailed Drilldown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: History of Runs */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-900 uppercase tracking-wider">Evaluation History</h3>
            <span className="text-xs font-medium text-slate-500">{runs.length} Runs</span>
          </div>
          <div className="divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
            {runs.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">
                No evaluation runs recorded yet. Click &quot;Run Evaluation&quot; to execute the test suite.
              </div>
            ) : (
              runs.map((r) => (
                <button
                  key={r.id}
                  onClick={() => handleSelectRun(r.id)}
                  className={`w-full text-left p-4 hover:bg-slate-50 transition flex items-center justify-between ${
                    selectedRun?.id === r.id ? 'bg-indigo-50/50 border-l-4 border-indigo-600' : ''
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-900">{r.dataset_id}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-mono">
                        v{r.dataset_version}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
                      <span>{new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      <span>•</span>
                      <span>{r.total_duration_ms.toFixed(0)} ms</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800">
                      {r.passed_cases}/{r.total_cases} Passed
                    </span>
                    <span className="block text-xs text-slate-400 mt-1 font-mono">
                      {(r.average_correctness * 100).toFixed(0)}% score
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Active Run Test Case Drilldown */}
        <div className="lg:col-span-2 bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden flex flex-col">
          <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 uppercase tracking-wider">
                Run Details {selectedRun ? `(${selectedRun.dataset_id} v${selectedRun.dataset_version})` : ''}
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                {selectedRun?.records ? `${selectedRun.records.length} test cases executed` : 'Select a run'}
              </p>
            </div>
            {selectedRun && (
              <div className="flex items-center gap-2">
                <span className="text-xs px-2.5 py-1 rounded-full font-medium bg-indigo-100 text-indigo-800 font-mono">
                  Duration: {selectedRun.total_duration_ms.toFixed(0)} ms
                </span>
                <span className="text-xs px-2.5 py-1 rounded-full font-medium bg-purple-100 text-purple-800 font-mono">
                  Tokens: {selectedRun.total_tokens}
                </span>
              </div>
            )}
          </div>

          <div className="flex-1 p-6 overflow-y-auto max-h-[600px] space-y-4">
            {!selectedRun?.records || selectedRun.records.length === 0 ? (
              <div className="text-center py-16 text-slate-400 text-sm">
                Select an evaluation run from the list to inspect test cases and scores.
              </div>
            ) : (
              selectedRun.records.map((rec) => (
                <div key={rec.id} className="p-4 rounded-lg border border-slate-200 bg-slate-50/50 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                        {rec.category}
                      </span>
                      <span className="text-xs font-mono text-slate-400">{rec.case_id}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-slate-500">{rec.latency_ms.toFixed(0)} ms</span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                          rec.status === 'PASSED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {rec.status}
                      </span>
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-slate-500">Query:</p>
                    <p className="text-sm font-medium text-slate-900 mt-0.5">{rec.query}</p>
                  </div>

                  {rec.actual_answer && (
                    <div>
                      <p className="text-xs font-semibold text-slate-500">Response / Outcome:</p>
                      <p className="text-sm text-slate-700 bg-white p-2.5 rounded border border-slate-200 mt-0.5">
                        {rec.actual_answer}
                      </p>
                    </div>
                  )}

                  <div className="flex items-center gap-4 text-xs font-mono pt-2 border-t border-slate-200/60 text-slate-600">
                    <span>Correctness: {(rec.correctness_score * 100).toFixed(0)}%</span>
                    <span>Groundedness: {(rec.groundedness_score * 100).toFixed(0)}%</span>
                    <span>Retrieval: {(rec.retrieval_score * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
