'use client';

import { useState, useEffect } from 'react';
import { Bot, Send, FileText, AlertCircle, Sparkles, Building2, HelpCircle } from 'lucide-react';
import api from '@/lib/api';
import { Organization, RAGQueryResponse, RAGSource } from '@/types';

export default function AssistantPage() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>('');
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RAGQueryResponse | null>(null);

  useEffect(() => {
    fetchOrganizations();
  }, []);

  const fetchOrganizations = async () => {
    try {
      const res = await api.get('/organizations/');
      setOrganizations(res.data);
      if (res.data.length > 0) {
        // Use stored org or default to first
        const storedOrgId = localStorage.getItem('current_org_id');
        if (storedOrgId && res.data.some((o: Organization) => o.id === storedOrgId)) {
          setSelectedOrgId(storedOrgId);
        } else {
          setSelectedOrgId(res.data[0].id);
          localStorage.setItem('current_org_id', res.data[0].id);
        }
      }
    } catch (err: any) {
      console.error('Failed to load organizations', err);
      setError('Could not load organizations. Please refresh.');
    }
  };

  const handleOrgChange = (orgId: string) => {
    setSelectedOrgId(orgId);
    localStorage.setItem('current_org_id', orgId);
    setResult(null);
    setError(null);
  };

  const handleQuery = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!question.trim() || !selectedOrgId || loading) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.post(
        `/rag/query?org_id=${selectedOrgId}`,
        {
          question: question.trim(),
          top_k: 5,
        }
      );
      setResult(res.data);
    } catch (err: any) {
      console.error('RAG query failed', err);
      setError(
        err.response?.data?.detail || 'An error occurred while querying the knowledge base.'
      );
    } finally {
      setLoading(false);
    }
  };

  const isNoAnswer = result?.answer.toLowerCase().includes("couldn't find this information") ||
                    result?.answer.toLowerCase().includes("could not find");

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">RAG Knowledge Assistant</h1>
            <span className="inline-flex items-center rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-700/10">
              Phase 6 Live
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Ask questions grounded strictly in your organization&apos;s indexed documents and pgvector embeddings.
          </p>
        </div>

        {/* Organization Selector */}
        <div className="flex items-center gap-2">
          <Building2 className="h-4 w-4 text-slate-400" />
          <span className="text-xs font-medium text-slate-600">Active Org:</span>
          <select
            id="assistant-org-select"
            value={selectedOrgId}
            onChange={(e) => handleOrgChange(e.target.value)}
            className="rounded-md border border-slate-300 bg-white py-1.5 px-3 text-xs font-medium text-slate-800 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Query Input Box */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
        <form onSubmit={handleQuery} className="space-y-3">
          <div className="relative">
            <textarea
              id="rag-question-input"
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask anything about your uploaded documents (e.g. 'What is the refund policy?' or 'Summarize key requirements')..."
              className="w-full resize-none rounded-lg border border-slate-200 p-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              disabled={loading}
            />
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
            {/* Sample query buttons */}
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className="font-medium">Suggestions:</span>
              <button
                type="button"
                onClick={() => setQuestion('What are the key terms in our documents?')}
                className="rounded-full bg-slate-100 hover:bg-slate-200 px-2.5 py-1 text-slate-700 transition"
              >
                Key terms
              </button>
              <button
                type="button"
                onClick={() => setQuestion('Summarize the document guidelines and obligations.')}
                className="rounded-full bg-slate-100 hover:bg-slate-200 px-2.5 py-1 text-slate-700 transition"
              >
                Summarize obligations
              </button>
            </div>

            <button
              id="rag-submit-button"
              type="submit"
              disabled={loading || !question.trim() || !selectedOrgId}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {loading ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  <span>Searching &amp; Reasoning...</span>
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  <span>Ask Knowledge Base</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-lg bg-rose-50 p-4 border border-rose-200 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-rose-500 shrink-0 mt-0.5" />
          <div className="text-sm text-rose-800">
            <p className="font-semibold">Query Failed</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* Loading state indicator */}
      {loading && (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-indigo-50 text-indigo-600 animate-pulse">
            <Sparkles className="h-6 w-6" />
          </div>
          <h3 className="text-sm font-semibold text-slate-800">Retrieving &amp; Synthesizing Grounded Answer</h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Computing query embedding, searching pgvector chunks with hybrid rank fusion, assembling context, and validating with LLM.
          </p>
        </div>
      )}

      {/* Result Section */}
      {result && !loading && (
        <div className="space-y-6">
          {/* Answer Card */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="bg-slate-50 border-b border-slate-200 px-5 py-3 flex items-center gap-2">
              <Bot className="h-5 w-5 text-indigo-600" />
              <h2 className="text-sm font-semibold text-slate-900">Grounded Response</h2>
            </div>
            
            <div className="p-6">
              {isNoAnswer ? (
                <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 flex items-start gap-3">
                  <HelpCircle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
                  <div className="text-sm text-amber-900">
                    <p className="font-semibold">No Answer Found in Knowledge Base</p>
                    <p className="mt-1">{result.answer}</p>
                    <p className="mt-2 text-xs text-amber-700">
                      Tip: Ensure you have uploaded relevant PDF, DOCX, or TXT documents to this organization on the Documents page.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="prose prose-sm max-w-none text-slate-800 whitespace-pre-line leading-relaxed">
                  {result.answer}
                </div>
              )}
            </div>
          </div>

          {/* Sources & Citations */}
          {result.sources && result.sources.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Sources &amp; Citations ({result.sources.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {result.sources.map((src: RAGSource, idx: number) => (
                  <div
                    key={src.chunk_id || idx}
                    className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:border-indigo-200 transition"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 truncate">
                        <FileText className="h-4 w-4 text-indigo-500 shrink-0" />
                        <span className="text-xs font-semibold text-slate-900 truncate" title={src.filename}>
                          {src.filename}
                        </span>
                      </div>
                      <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                        Score: {(src.score * 100).toFixed(0)}%
                      </span>
                    </div>

                    <div className="mt-2 flex items-center gap-4 text-[11px] text-slate-500">
                      {src.page !== null && <span>Page: {src.page}</span>}
                      <span>Chunk: #{src.chunk_index}</span>
                      <span className="truncate max-w-[120px]" title={src.document_id}>
                        Doc: {src.document_id.slice(0, 8)}...
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
