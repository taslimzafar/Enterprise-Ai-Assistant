"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { 
  Workflow as WorkflowIcon, 
  Play, 
  Plus, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  AlertCircle, 
  RefreshCw,
  Archive,
  ArrowRight,
  ShieldAlert,
  Pause,
  RotateCcw,
  Ban,
  ChevronDown,
  ChevronUp,
  Layers,
  Sparkles
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import { Workflow, WorkflowExecution, StepType } from '@/types';

export default function WorkflowsPage() {
  const { activeOrganization } = useAuth();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [executionsLoading, setExecutionsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [expandedExecId, setExpandedExecId] = useState<string | null>(null);

  // New workflow form state
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newSteps, setNewSteps] = useState<Array<{
    name: string;
    type: StepType;
    output_key: string;
    timeout_seconds: number;
    retry_count: number;
    requires_approval: boolean;
    configuration: string;
    input_mapping: string;
  }>>([
    {
      name: 'Fetch Statistics',
      type: 'ORGANIZATION_STATS',
      output_key: 'org_stats',
      timeout_seconds: 30,
      retry_count: 1,
      requires_approval: false,
      configuration: '{}',
      input_mapping: '{}',
    },
    {
      name: 'Draft Summary',
      type: 'LLM_GENERATION',
      output_key: 'summary',
      timeout_seconds: 45,
      retry_count: 0,
      requires_approval: false,
      configuration: '{"prompt": "Summarize organization stats: {org_stats}"}',
      input_mapping: '{}',
    }
  ]);

  const fetchWorkflows = useCallback(async () => {
    if (!activeOrganization) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.get('/workflows', {
        params: { org_id: activeOrganization.id },
      });
      const items = res.data.items || [];
      setWorkflows(items);
      if (items.length > 0 && !selectedWorkflow) {
        setSelectedWorkflow(items[0]);
      }
    } catch (err: any) {
      console.error('Failed to fetch workflows:', err);
      setErrorMessage(err.response?.data?.detail || 'Failed to load workflows.');
    } finally {
      setLoading(false);
    }
  }, [activeOrganization, selectedWorkflow]);

  const fetchExecutions = useCallback(async (workflowId: string) => {
    if (!activeOrganization) return;
    setExecutionsLoading(true);
    try {
      const res = await api.get(`/workflows/${workflowId}/executions`, {
        params: { org_id: activeOrganization.id },
      });
      setExecutions(res.data.items || []);
    } catch (err: any) {
      console.error('Failed to fetch executions:', err);
    } finally {
      setExecutionsLoading(false);
    }
  }, [activeOrganization]);

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  useEffect(() => {
    if (selectedWorkflow) {
      fetchExecutions(selectedWorkflow.id);
    } else {
      setExecutions([]);
    }
  }, [selectedWorkflow, fetchExecutions]);

  const handleActivate = async (id: string) => {
    if (!activeOrganization) return;
    setActionLoading(id);
    try {
      const res = await api.post(`/workflows/${id}/activate?org_id=${activeOrganization.id}`);
      setWorkflows(prev => prev.map(w => (w.id === id ? res.data : w)));
      if (selectedWorkflow?.id === id) setSelectedWorkflow(res.data);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to activate workflow.');
    } finally {
      setActionLoading(null);
    }
  };

  const handleArchive = async (id: string) => {
    if (!activeOrganization) return;
    setActionLoading(id);
    try {
      const res = await api.post(`/workflows/${id}/archive?org_id=${activeOrganization.id}`);
      setWorkflows(prev => prev.map(w => (w.id === id ? res.data : w)));
      if (selectedWorkflow?.id === id) setSelectedWorkflow(res.data);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to archive workflow.');
    } finally {
      setActionLoading(null);
    }
  };

  const handleExecute = async (id: string) => {
    if (!activeOrganization) return;
    setActionLoading(id);
    try {
      await api.post(`/workflows/${id}/execute?org_id=${activeOrganization.id}`, {
        initial_inputs: { triggered_by: 'Dashboard UI' }
      });
      await fetchExecutions(id);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to trigger workflow execution.');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCreateWorkflow = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOrganization) return;
    setErrorMessage(null);

    try {
      const stepsPayload = newSteps.map((s, idx) => ({
        name: s.name,
        type: s.type,
        order: idx,
        output_key: s.output_key,
        timeout_seconds: Number(s.timeout_seconds),
        retry_count: Number(s.retry_count),
        requires_approval: s.requires_approval,
        configuration: JSON.parse(s.configuration || '{}'),
        input_mapping: JSON.parse(s.input_mapping || '{}'),
      }));

      const res = await api.post(`/workflows?org_id=${activeOrganization.id}`, {
        name: newName,
        description: newDesc,
        steps: stepsPayload,
      });

      setWorkflows(prev => [res.data, ...prev]);
      setSelectedWorkflow(res.data);
      setIsCreateOpen(false);
      setNewName('');
      setNewDesc('');
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || err.message || 'Failed to create workflow.');
    }
  };

  const addStep = () => {
    setNewSteps(prev => [
      ...prev,
      {
        name: `Step ${prev.length + 1}`,
        type: 'CALCULATOR',
        output_key: `step_${prev.length + 1}`,
        timeout_seconds: 30,
        retry_count: 0,
        requires_approval: false,
        configuration: '{"expression": "100 * 2"}',
        input_mapping: '{}',
      }
    ]);
  };

  const removeStep = (idx: number) => {
    setNewSteps(prev => prev.filter((_, i) => i !== idx));
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ACTIVE':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">Active</span>;
      case 'DRAFT':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">Draft</span>;
      case 'ARCHIVED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-800">Archived</span>;
      case 'RUNNING':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">Running</span>;
      case 'WAITING_APPROVAL':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">Waiting Approval</span>;
      case 'COMPLETED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800">Completed</span>;
      case 'FAILED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">Failed</span>;
      case 'SKIPPED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">Skipped</span>;
      case 'CANCELLED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">Cancelled</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">{status}</span>;
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <WorkflowIcon className="h-6 w-6 text-indigo-600" />
            Enterprise Workflows
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Build, activate, and observe multi-step deterministic agent workflows with state persistence and human approval.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchWorkflows()}
            className="p-2 border border-slate-300 rounded-md text-slate-600 hover:bg-slate-50"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-md shadow-sm transition"
          >
            <Plus className="h-4 w-4 mr-1.5" />
            New Workflow
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="rounded-md bg-red-50 p-4 border border-red-200">
          <div className="flex">
            <AlertCircle className="h-5 w-5 text-red-400 mr-2" />
            <div className="text-sm text-red-700">{errorMessage}</div>
          </div>
        </div>
      )}

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Workflows List */}
        <div className="lg:col-span-1 bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden flex flex-col h-[750px]">
          <div className="p-4 border-b border-slate-200 bg-slate-50">
            <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-2">
              <Layers className="h-4 w-4 text-indigo-500" />
              Workflow Catalog ({workflows.length})
            </h2>
          </div>
          <div className="divide-y divide-slate-100 overflow-y-auto flex-1">
            {loading ? (
              <div className="p-8 text-center text-slate-400">Loading workflows...</div>
            ) : workflows.length === 0 ? (
              <div className="p-8 text-center text-slate-400">
                No workflows found. Create your first automated workflow!
              </div>
            ) : (
              workflows.map(wf => (
                <div
                  key={wf.id}
                  onClick={() => setSelectedWorkflow(wf)}
                  className={`p-4 cursor-pointer transition ${
                    selectedWorkflow?.id === wf.id
                      ? 'bg-indigo-50/70 border-l-4 border-indigo-600'
                      : 'hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">{wf.name}</h3>
                    {getStatusBadge(wf.status)}
                  </div>
                  <p className="text-xs text-slate-500 line-clamp-2 mt-1">{wf.description || 'No description provided.'}</p>
                  <div className="flex items-center justify-between text-xs text-slate-400 mt-2.5">
                    <span>{wf.steps.length} Steps</span>
                    <span>v{wf.version}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Columns: Workflow Detail & Executions */}
        <div className="lg:col-span-2 space-y-6">
          {selectedWorkflow ? (
            <>
              {/* Selected Workflow Header & Controls */}
              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-4">
                  <div>
                    <div className="flex items-center gap-2.5">
                      <h2 className="text-xl font-bold text-slate-900">{selectedWorkflow.name}</h2>
                      {getStatusBadge(selectedWorkflow.status)}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">{selectedWorkflow.description || 'No description provided.'}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {selectedWorkflow.status === 'DRAFT' && (
                      <button
                        onClick={() => handleActivate(selectedWorkflow.id)}
                        disabled={actionLoading === selectedWorkflow.id}
                        className="inline-flex items-center px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded shadow-sm"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                        Activate
                      </button>
                    )}
                    {selectedWorkflow.status === 'ACTIVE' && (
                      <button
                        onClick={() => handleExecute(selectedWorkflow.id)}
                        disabled={actionLoading === selectedWorkflow.id}
                        className="inline-flex items-center px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded shadow-sm"
                      >
                        <Play className="h-3.5 w-3.5 mr-1" />
                        Execute
                      </button>
                    )}
                    {selectedWorkflow.status !== 'ARCHIVED' && (
                      <button
                        onClick={() => handleArchive(selectedWorkflow.id)}
                        disabled={actionLoading === selectedWorkflow.id}
                        className="inline-flex items-center px-3 py-1.5 border border-slate-300 text-slate-700 hover:bg-slate-50 text-xs font-medium rounded"
                      >
                        <Archive className="h-3.5 w-3.5 mr-1" />
                        Archive
                      </button>
                    )}
                  </div>
                </div>

                {/* Steps Flowchart */}
                <div className="mt-5">
                  <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-3">
                    Execution Pipeline ({selectedWorkflow.steps.length} Steps)
                  </h3>
                  <div className="flex items-center overflow-x-auto pb-3 gap-2">
                    {selectedWorkflow.steps.map((step, idx) => (
                      <React.Fragment key={step.id}>
                        <div className="min-w-[170px] p-3 rounded-lg border border-slate-200 bg-slate-50 text-left shrink-0">
                          <div className="flex items-center justify-between text-xs text-slate-400 font-mono mb-1">
                            <span>Step {idx + 1}</span>
                            {step.requires_approval && (
                              <span title="Requires Human Approval">
                                <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
                              </span>
                            )}
                          </div>
                          <div className="text-xs font-semibold text-slate-800 truncate">{step.name}</div>
                          <div className="text-[11px] text-indigo-600 font-medium mt-0.5">{step.type}</div>
                          <div className="text-[10px] text-slate-400 mt-2">Outputs: <span className="font-mono text-slate-600">{step.output_key}</span></div>
                        </div>
                        {idx < selectedWorkflow.steps.length - 1 && (
                          <ArrowRight className="h-4 w-4 text-slate-300 shrink-0" />
                        )}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </div>

              {/* Execution History */}
              <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                    <Clock className="h-4 w-4 text-slate-500" />
                    Execution History
                  </h3>
                  <button
                    onClick={() => fetchExecutions(selectedWorkflow.id)}
                    className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1 font-medium"
                  >
                    <RefreshCw className="h-3 w-3" /> Refresh
                  </button>
                </div>

                {executionsLoading ? (
                  <div className="py-8 text-center text-slate-400 text-sm">Loading execution logs...</div>
                ) : executions.length === 0 ? (
                  <div className="py-8 text-center text-slate-400 text-sm">
                    No executions yet. Click 'Execute' to run this workflow.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {executions.map(exec => (
                      <div key={exec.id} className="border border-slate-200 rounded-md overflow-hidden">
                        <div
                          onClick={() => setExpandedExecId(expandedExecId === exec.id ? null : exec.id)}
                          className="p-3 bg-slate-50 hover:bg-slate-100 flex items-center justify-between cursor-pointer transition"
                        >
                          <div className="flex items-center gap-3">
                            {getStatusBadge(exec.status)}
                            <span className="text-xs font-mono text-slate-600">ID: {exec.id.slice(0, 8)}...</span>
                            <span className="text-xs text-slate-400">
                              {new Date(exec.created_at).toLocaleTimeString()}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            {exec.error && <span className="text-xs text-red-500 truncate max-w-xs">{exec.error}</span>}
                            {expandedExecId === exec.id ? (
                              <ChevronUp className="h-4 w-4 text-slate-400" />
                            ) : (
                              <ChevronDown className="h-4 w-4 text-slate-400" />
                            )}
                          </div>
                        </div>

                        {expandedExecId === exec.id && (
                          <div className="p-4 bg-white border-t border-slate-200 space-y-3">
                            <h4 className="text-xs font-semibold text-slate-700 uppercase">Step Execution Breakdown</h4>
                            <div className="space-y-2">
                              {exec.step_executions?.map(stepExec => (
                                <div key={stepExec.id} className="p-2.5 rounded bg-slate-50 border border-slate-100 flex items-center justify-between text-xs">
                                  <div className="space-y-0.5">
                                    <div className="font-medium text-slate-800 flex items-center gap-2">
                                      <span>Step ID: {stepExec.step_id.slice(0, 8)}...</span>
                                      {getStatusBadge(stepExec.status)}
                                    </div>
                                    {stepExec.retry_attempts > 0 && (
                                      <span className="text-slate-400 text-[11px]">Retries: {stepExec.retry_attempts}</span>
                                    )}
                                    {stepExec.approval_id && (
                                      <div className="text-amber-600 text-[11px]">Approval Ref: {stepExec.approval_id}</div>
                                    )}
                                  </div>
                                  <div className="text-right">
                                    {stepExec.error ? (
                                      <span className="text-red-500 font-mono">{stepExec.error}</span>
                                    ) : (
                                      <span className="text-emerald-600 font-mono">Outputs recorded</span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                            {exec.context_data && Object.keys(exec.context_data).length > 0 && (
                              <div className="mt-3">
                                <h4 className="text-xs font-semibold text-slate-700 uppercase mb-1">State Context Output</h4>
                                <pre className="p-2.5 bg-slate-900 text-slate-100 rounded text-xs overflow-x-auto max-h-40">
                                  {JSON.stringify(exec.context_data, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-12 text-center text-slate-400">
              Select or create a workflow to view its pipeline configuration.
            </div>
          )}
        </div>
      </div>

      {/* Create Workflow Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-lg max-w-2xl w-full p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-indigo-600" />
                Configure New Workflow
              </h3>
              <button onClick={() => setIsCreateOpen(false)} className="text-slate-400 hover:text-slate-600">
                <XCircle className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleCreateWorkflow} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700">Workflow Name</label>
                <input
                  type="text"
                  required
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  placeholder="e.g. Weekly KPI Digest"
                  className="mt-1 block w-full rounded border-slate-300 shadow-sm text-sm p-2 border"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700">Description</label>
                <textarea
                  rows={2}
                  value={newDesc}
                  onChange={e => setNewDesc(e.target.value)}
                  placeholder="Automated pipeline querying organization metrics and generating reports."
                  className="mt-1 block w-full rounded border-slate-300 shadow-sm text-sm p-2 border"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-semibold text-slate-700 uppercase">Sequential Steps</label>
                  <button
                    type="button"
                    onClick={addStep}
                    className="text-xs text-indigo-600 font-medium hover:underline flex items-center gap-1"
                  >
                    <Plus className="h-3 w-3" /> Add Step
                  </button>
                </div>

                <div className="space-y-3">
                  {newSteps.map((step, idx) => (
                    <div key={idx} className="p-3 border border-slate-200 rounded-md bg-slate-50 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-700">Step {idx + 1}</span>
                        {newSteps.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeStep(idx)}
                            className="text-red-500 hover:text-red-700 text-xs"
                          >
                            Remove
                          </button>
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-[11px] text-slate-600">Name</label>
                          <input
                            type="text"
                            required
                            value={step.name}
                            onChange={e => {
                              const updated = [...newSteps];
                              updated[idx].name = e.target.value;
                              setNewSteps(updated);
                            }}
                            className="w-full text-xs p-1.5 border rounded"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-slate-600">Type</label>
                          <select
                            value={step.type}
                            onChange={e => {
                              const updated = [...newSteps];
                              updated[idx].type = e.target.value as StepType;
                              setNewSteps(updated);
                            }}
                            className="w-full text-xs p-1.5 border rounded bg-white"
                          >
                            <option value="ORGANIZATION_STATS">ORGANIZATION_STATS</option>
                            <option value="KNOWLEDGE_SEARCH">KNOWLEDGE_SEARCH</option>
                            <option value="CALCULATOR">CALCULATOR</option>
                            <option value="DEMO_NOTE">DEMO_NOTE (HITL)</option>
                            <option value="LLM_GENERATION">LLM_GENERATION</option>
                          </select>
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <label className="block text-[11px] text-slate-600">Output Key</label>
                          <input
                            type="text"
                            required
                            value={step.output_key}
                            onChange={e => {
                              const updated = [...newSteps];
                              updated[idx].output_key = e.target.value;
                              setNewSteps(updated);
                            }}
                            className="w-full text-xs p-1.5 border rounded font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-slate-600">Timeout (s)</label>
                          <input
                            type="number"
                            min="1"
                            max="300"
                            value={step.timeout_seconds}
                            onChange={e => {
                              const updated = [...newSteps];
                              updated[idx].timeout_seconds = parseInt(e.target.value) || 30;
                              setNewSteps(updated);
                            }}
                            className="w-full text-xs p-1.5 border rounded"
                          />
                        </div>
                        <div className="flex items-center pt-4">
                          <label className="flex items-center gap-1.5 text-[11px] text-slate-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={step.requires_approval}
                              onChange={e => {
                                const updated = [...newSteps];
                                updated[idx].requires_approval = e.target.checked;
                                setNewSteps(updated);
                              }}
                              className="rounded border-slate-300 text-indigo-600"
                            />
                            Require HITL Approval
                          </label>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 border border-slate-300 text-slate-700 text-xs font-medium rounded hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded shadow-sm"
                >
                  Create Workflow
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
