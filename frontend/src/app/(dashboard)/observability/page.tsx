"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { 
  Activity, 
  RefreshCw, 
  AlertCircle, 
  Clock, 
  Cpu, 
  Wrench, 
  Workflow, 
  ShieldCheck, 
  AlertTriangle,
  Server,
  Zap
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';

interface ObservabilityMetrics {
  request_count: number;
  error_count: number;
  error_rate: number;
  latency_summary: {
    count: number;
    average_ms: number;
    p50_ms: number;
    p95_ms: number;
    p99_ms: number;
    min_ms: number;
    max_ms: number;
  };
  tokens: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost: string;
  };
  tool_usage: Record<string, number>;
  workflow_executions: number;
  approval_waits: number;
  error_categories: Record<string, number>;
}

export default function ObservabilityPage() {
  const { activeOrganization } = useAuth();
  const [metrics, setMetrics] = useState<ObservabilityMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    if (!activeOrganization) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.get(`/observability/metrics?org_id=${activeOrganization.id}`);
      setMetrics(res.data);
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || 'Failed to load observability metrics');
    } finally {
      setLoading(false);
    }
  }, [activeOrganization]);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Activity className="w-6 h-6 text-indigo-600" />
            Observability & Telemetry
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time performance monitoring, trace latency distributions, token metrics, and error rates
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchMetrics}
            disabled={loading}
            className="inline-flex items-center px-4 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition shadow-sm"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md flex items-center gap-3 text-red-700">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <p className="text-sm">{errorMessage}</p>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Requests</span>
            <Server className="w-5 h-5 text-indigo-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? metrics.request_count.toLocaleString() : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">Operational executions</span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Error Rate</span>
            <AlertTriangle className={`w-5 h-5 ${metrics && metrics.error_rate > 0.05 ? 'text-red-500' : 'text-emerald-500'}`} />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? `${(metrics.error_rate * 100).toFixed(2)}%` : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">
            {metrics ? `${metrics.error_count} failed requests` : '0 errors'}
          </span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">p50 / p95 Latency</span>
            <Clock className="w-5 h-5 text-amber-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? `${metrics.latency_summary.p50_ms.toFixed(0)} / ${metrics.latency_summary.p95_ms.toFixed(0)} ms` : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">
            p99: {metrics ? `${metrics.latency_summary.p99_ms.toFixed(0)} ms` : '--'}
          </span>
        </div>

        <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Token Usage</span>
            <Cpu className="w-5 h-5 text-purple-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {metrics ? metrics.tokens.total_tokens.toLocaleString() : '--'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">
            Cost: {metrics ? metrics.tokens.estimated_cost : 'unavailable'}
          </span>
        </div>
      </div>

      {/* Secondary Row: Execution Counters */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex items-center gap-4">
          <div className="p-3 bg-blue-50 text-blue-600 rounded-lg">
            <Wrench className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 uppercase">Tool Calls</span>
            <p className="text-xl font-bold text-slate-900">
              {metrics ? Object.values(metrics.tool_usage).reduce((a, b) => a + b, 0) : 0}
            </p>
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex items-center gap-4">
          <div className="p-3 bg-indigo-50 text-indigo-600 rounded-lg">
            <Workflow className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 uppercase">Workflows Executed</span>
            <p className="text-xl font-bold text-slate-900">
              {metrics ? metrics.workflow_executions : 0}
            </p>
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex items-center gap-4">
          <div className="p-3 bg-amber-50 text-amber-600 rounded-lg">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 uppercase">HITL Approvals Paused</span>
            <p className="text-xl font-bold text-slate-900">
              {metrics ? metrics.approval_waits : 0}
            </p>
          </div>
        </div>
      </div>

      {/* Latency Percentiles & Error Breakdown Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Latency Percentiles Table */}
        <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
          <h3 className="text-base font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-500" />
            Latency Distribution Summary
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 text-xs uppercase">
                <tr>
                  <th className="py-2.5 px-4">Metric</th>
                  <th className="py-2.5 px-4 text-right">Value (ms)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono text-xs">
                <tr>
                  <td className="py-2.5 px-4 font-sans font-medium text-slate-700">Average Latency</td>
                  <td className="py-2.5 px-4 text-right font-bold text-slate-900">{metrics?.latency_summary.average_ms ?? 0} ms</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-sans font-medium text-slate-700">p50 (Median)</td>
                  <td className="py-2.5 px-4 text-right font-bold text-indigo-600">{metrics?.latency_summary.p50_ms ?? 0} ms</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-sans font-medium text-slate-700">p95 (95th Percentile)</td>
                  <td className="py-2.5 px-4 text-right font-bold text-amber-600">{metrics?.latency_summary.p95_ms ?? 0} ms</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-sans font-medium text-slate-700">p99 (99th Percentile)</td>
                  <td className="py-2.5 px-4 text-right font-bold text-red-600">{metrics?.latency_summary.p99_ms ?? 0} ms</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-4 font-sans font-medium text-slate-700">Min / Max</td>
                  <td className="py-2.5 px-4 text-right text-slate-600">
                    {metrics?.latency_summary.min_ms ?? 0} / {metrics?.latency_summary.max_ms ?? 0} ms
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Normalized Error Categories */}
        <div className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm">
          <h3 className="text-base font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-500" />
            Normalized Error Categories
          </h3>
          {!metrics || Object.keys(metrics.error_categories).length === 0 ? (
            <div className="text-center py-10 text-slate-400 text-sm">
              No runtime errors recorded. All systems healthy.
            </div>
          ) : (
            <div className="space-y-3">
              {Object.entries(metrics.error_categories).map(([category, count]) => (
                <div key={category} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200">
                  <span className="text-xs font-mono font-bold text-slate-700">{category}</span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-800">
                    {count} {count === 1 ? 'failure' : 'failures'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
