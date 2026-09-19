"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { 
  ShieldCheck, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  AlertCircle, 
  Filter, 
  RefreshCw,
  Ban,
  ChevronDown,
  ChevronUp,
  User as UserIcon,
  Calendar,
  AlertTriangle
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import { Approval, ApprovalStatus } from '@/types';

export default function ApprovalsPage() {
  const { user, activeOrganization } = useAuth();
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [rejectModalId, setRejectModalId] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState<string>('');

  const fetchApprovals = useCallback(async () => {
    if (!activeOrganization) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const params: Record<string, string> = { org_id: activeOrganization.id };
      if (selectedStatus !== 'ALL') {
        params.status = selectedStatus;
      }
      const res = await api.get('/approvals', { params });
      setApprovals(res.data.items || []);
    } catch (err: any) {
      console.error('Failed to fetch approvals:', err);
      setErrorMessage(err.response?.data?.detail || 'Failed to load approval requests.');
    } finally {
      setLoading(false);
    }
  }, [activeOrganization, selectedStatus]);

  useEffect(() => {
    fetchApprovals();
  }, [fetchApprovals]);

  const handleApprove = async (approvalId: string) => {
    if (!activeOrganization) return;
    setActionLoading(approvalId);
    setErrorMessage(null);
    try {
      await api.post(`/approvals/${approvalId}/approve?org_id=${activeOrganization.id}`);
      await fetchApprovals();
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || 'Failed to approve request.');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (approvalId: string) => {
    if (!activeOrganization) return;
    setActionLoading(approvalId);
    setErrorMessage(null);
    try {
      await api.post(`/approvals/${approvalId}/reject?org_id=${activeOrganization.id}`, {
        rejection_reason: rejectionReason.trim() || 'Rejected by authorized reviewer.',
      });
      setRejectModalId(null);
      setRejectionReason('');
      await fetchApprovals();
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || 'Failed to reject request.');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async (approvalId: string) => {
    if (!activeOrganization) return;
    setActionLoading(approvalId);
    setErrorMessage(null);
    try {
      await api.post(`/approvals/${approvalId}/cancel?org_id=${activeOrganization.id}`);
      await fetchApprovals();
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || 'Failed to cancel request.');
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusBadge = (status: ApprovalStatus) => {
    switch (status) {
      case 'PENDING':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Clock className="w-3.5 h-3.5" /> Pending Review
          </span>
        );
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" /> Approved
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <XCircle className="w-3.5 h-3.5" /> Rejected
          </span>
        );
      case 'EXPIRED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-400 border border-slate-500/20">
            <AlertCircle className="w-3.5 h-3.5" /> Expired
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-400 border border-slate-500/20">
            <Ban className="w-3.5 h-3.5" /> Cancelled
          </span>
        );
      default:
        return null;
    }
  };

  const isUserRequester = (approval: Approval): boolean => {
    return Boolean(user && user.id === approval.requested_by_user_id);
  };

  return (
    <div className="flex-1 overflow-y-auto p-8 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Human-in-the-Loop Approvals</h1>
              <p className="text-sm text-slate-400">
                Review and authorize sensitive AI tool executions across your organization.
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchApprovals}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors border border-slate-700"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {errorMessage && (
        <div className="mt-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button 
            onClick={() => setErrorMessage(null)} 
            className="text-xs hover:underline text-rose-400"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filters Bar */}
      <div className="mt-6 flex flex-wrap items-center gap-2 pb-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 mr-2 uppercase tracking-wider">
          <Filter className="w-3.5 h-3.5" /> Status Filter:
        </div>
        {['ALL', 'PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED'].map((status) => (
          <button
            key={status}
            onClick={() => setSelectedStatus(status)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              selectedStatus === status
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20 font-semibold'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700/60'
            }`}
          >
            {status === 'ALL' ? 'All Requests' : status.charAt(0) + status.slice(1).toLowerCase()}
          </button>
        ))}
      </div>

      {/* Approvals List */}
      <div className="mt-6 space-y-4">
        {loading && approvals.length === 0 ? (
          <div className="p-12 text-center text-slate-400 bg-slate-900/50 rounded-2xl border border-slate-800">
            <RefreshCw className="w-8 h-8 animate-spin mx-auto text-indigo-500 mb-3" />
            <p className="text-sm">Loading approval records...</p>
          </div>
        ) : approvals.length === 0 ? (
          <div className="p-12 text-center text-slate-400 bg-slate-900/40 rounded-2xl border border-slate-800/60">
            <ShieldCheck className="w-12 h-12 mx-auto text-slate-600 mb-3" />
            <h3 className="text-base font-semibold text-slate-300">No approval requests found</h3>
            <p className="text-xs text-slate-500 mt-1">
              {selectedStatus === 'ALL' 
                ? 'No sensitive tool executions have requested human authorization yet.' 
                : `No requests with status "${selectedStatus}".`}
            </p>
          </div>
        ) : (
          approvals.map((approval) => {
            const isPending = approval.status === 'PENDING';
            const isRequester = isUserRequester(approval);
            const isExpanded = expandedId === approval.id;

            return (
              <div 
                key={approval.id} 
                className="bg-slate-900/70 border border-slate-800 rounded-xl overflow-hidden transition-all hover:border-slate-700 shadow-sm"
              >
                {/* Main Card Summary */}
                <div className="p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="mt-1">
                      {getStatusBadge(approval.status)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-mono font-bold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                          {approval.tool_name}
                        </span>
                        <span className="text-xs text-slate-500">•</span>
                        <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
                          Action: {approval.action_type}
                        </span>
                      </div>
                      <h4 className="text-base font-semibold text-white mt-1.5">
                        {approval.reason || 'Authorization requested for sensitive tool execution.'}
                      </h4>
                      <div className="flex flex-wrap items-center gap-4 mt-2 text-xs text-slate-400">
                        <span className="flex items-center gap-1.5">
                          <UserIcon className="w-3.5 h-3.5 text-slate-500" />
                          Requested by: <span className="font-mono text-slate-300">{approval.requested_by_user_id.slice(0, 8)}...</span>
                          {isRequester && <span className="text-indigo-400 font-semibold">(You)</span>}
                        </span>
                        <span className="flex items-center gap-1.5">
                          <Calendar className="w-3.5 h-3.5 text-slate-500" />
                          {new Date(approval.created_at).toLocaleString()}
                        </span>
                        {approval.expires_at && (
                          <span className="flex items-center gap-1.5 text-amber-400/90">
                            <Clock className="w-3.5 h-3.5 text-amber-500" />
                            Expires: {new Date(approval.expires_at).toLocaleTimeString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions & Expansion */}
                  <div className="flex items-center gap-2 self-end lg:self-center">
                    {isPending && (
                      <>
                        <button
                          onClick={() => handleApprove(approval.id)}
                          disabled={actionLoading === approval.id || isRequester}
                          title={isRequester ? "Anti-self-approval: Requester cannot approve their own action" : "Approve tool execution"}
                          className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                            isRequester
                              ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                              : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/20'
                          }`}
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Approve
                        </button>

                        <button
                          onClick={() => setRejectModalId(approval.id)}
                          disabled={actionLoading === approval.id}
                          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-rose-600/20 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500/30 transition-all"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          Reject
                        </button>

                        {isRequester && (
                          <button
                            onClick={() => handleCancel(approval.id)}
                            disabled={actionLoading === approval.id}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all"
                          >
                            <Ban className="w-3.5 h-3.5" />
                            Cancel
                          </button>
                        )}
                      </>
                    )}

                    <button
                      onClick={() => setExpandedId(isExpanded ? null : approval.id)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                      title={isExpanded ? "Collapse details" : "Expand parameters"}
                    >
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Expanded Details / Safe Arguments */}
                {isExpanded && (
                  <div className="border-t border-slate-800/80 bg-slate-950/40 p-5 space-y-3">
                    <div>
                      <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                        Tool Arguments (Payload)
                      </h5>
                      <pre className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-xs font-mono text-emerald-400 overflow-x-auto">
                        {JSON.stringify(approval.action_arguments, null, 2)}
                      </pre>
                    </div>

                    {approval.rejection_reason && (
                      <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-300">
                        <span className="font-semibold">Rejection Note: </span>
                        {approval.rejection_reason}
                      </div>
                    )}

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs text-slate-400 pt-2 border-t border-slate-800/60">
                      <div>
                        <span className="block text-slate-500">Approval ID:</span>
                        <span className="font-mono text-slate-300">{approval.id}</span>
                      </div>
                      <div>
                        <span className="block text-slate-500">Conversation ID:</span>
                        <span className="font-mono text-slate-300">{approval.conversation_id || 'N/A'}</span>
                      </div>
                      <div>
                        <span className="block text-slate-500">Approved By:</span>
                        <span className="font-mono text-slate-300">{approval.approved_by_user_id || 'None'}</span>
                      </div>
                      <div>
                        <span className="block text-slate-500">Last Updated:</span>
                        <span className="text-slate-300">{approval.updated_at ? new Date(approval.updated_at).toLocaleString() : 'N/A'}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Reject Modal */}
      {rejectModalId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-rose-400">
              <div className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/20">
                <XCircle className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-bold text-white">Reject Approval Request</h3>
            </div>
            <p className="text-xs text-slate-400">
              Please provide a reason for rejecting this tool execution. This justification will be logged and returned to the requester.
            </p>
            <div>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Reason for rejection (e.g. Unauthorized operation, missing prerequisites)..."
                className="w-full h-24 bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500 transition-colors resize-none"
              />
            </div>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => {
                  setRejectModalId(null);
                  setRejectionReason('');
                }}
                className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleReject(rejectModalId)}
                disabled={actionLoading === rejectModalId}
                className="px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-500 rounded-lg transition-colors shadow-lg shadow-rose-600/20"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
