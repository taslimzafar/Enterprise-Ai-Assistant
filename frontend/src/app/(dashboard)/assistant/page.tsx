'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Bot,
  Send,
  Plus,
  Trash2,
  Edit2,
  Check,
  X,
  Square,
  MessageSquare,
  Copy,
  ChevronDown,
  ChevronUp,
  FileText,
  Sparkles,
  Building2,
  AlertCircle,
  Search,
  CheckCheck,
} from 'lucide-react';
import api from '@/lib/api';
import { Organization, Conversation, Message, RAGSource } from '@/types';

export default function AssistantChatPage() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>('');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingTitleId, setEditingTitleId] = useState<string | null>(null);
  const [editTitleText, setEditTitleText] = useState('');
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [agentStatus, setAgentStatus] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming]);

  // Load organizations on initial mount
  useEffect(() => {
    fetchOrganizations();
  }, []);

  // Fetch conversations when selected organization changes
  useEffect(() => {
    if (selectedOrgId) {
      fetchConversations(selectedOrgId);
    } else {
      setConversations([]);
      setMessages([]);
      setActiveConversationId(null);
    }
  }, [selectedOrgId]);

  // Fetch messages when active conversation changes
  useEffect(() => {
    if (activeConversationId && selectedOrgId) {
      fetchMessages(activeConversationId, selectedOrgId);
    } else {
      setMessages([]);
    }
  }, [activeConversationId]);

  const fetchOrganizations = async () => {
    try {
      const res = await api.get('/organizations/');
      setOrganizations(res.data);
      if (res.data.length > 0) {
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
    setActiveConversationId(null);
    setMessages([]);
    setError(null);
  };

  const fetchConversations = async (orgId: string) => {
    setLoadingConversations(true);
    try {
      const res = await api.get(`/conversations?org_id=${orgId}`);
      setConversations(res.data);
      if (res.data.length > 0) {
        setActiveConversationId(res.data[0].id);
      } else {
        setActiveConversationId(null);
      }
    } catch (err: any) {
      console.error('Failed to load conversations', err);
      setError(err.response?.data?.detail || 'Could not load conversations.');
    } finally {
      setLoadingConversations(false);
    }
  };

  const fetchMessages = async (convId: string, orgId: string) => {
    setLoadingMessages(true);
    try {
      const res = await api.get(`/conversations/${convId}/messages?org_id=${orgId}`);
      setMessages(res.data);
    } catch (err: any) {
      console.error('Failed to load messages', err);
    } finally {
      setLoadingMessages(false);
    }
  };

  const handleCreateNewChat = async () => {
    if (!selectedOrgId || isStreaming) return;
    try {
      const res = await api.post(`/conversations?org_id=${selectedOrgId}`, {
        title: 'New Chat',
      });
      const newConv = res.data;
      setConversations((prev) => [newConv, ...prev]);
      setActiveConversationId(newConv.id);
      setMessages([]);
      setInput('');
      if (textareaRef.current) textareaRef.current.focus();
    } catch (err: any) {
      console.error('Failed to create new conversation', err);
      setError('Failed to create conversation.');
    }
  };

  const handleSaveTitle = async (convId: string) => {
    if (!editTitleText.trim()) {
      setEditingTitleId(null);
      return;
    }
    try {
      const res = await api.patch(
        `/conversations/${convId}?org_id=${selectedOrgId}`,
        { title: editTitleText.trim() }
      );
      setConversations((prev) =>
        prev.map((c) => (c.id === convId ? { ...c, title: res.data.title } : c))
      );
      setEditingTitleId(null);
    } catch (err) {
      console.error('Failed to update title', err);
    }
  };

  const handleDeleteConversation = async (e: React.MouseEvent, convId: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this conversation?')) return;
    try {
      await api.delete(`/conversations/${convId}?org_id=${selectedOrgId}`);
      const remaining = conversations.filter((c) => c.id !== convId);
      setConversations(remaining);
      if (activeConversationId === convId) {
        setActiveConversationId(remaining.length > 0 ? remaining[0].id : null);
      }
    } catch (err) {
      console.error('Failed to delete conversation', err);
    }
  };

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant' && last.status === 'streaming') {
          return [
            ...prev.slice(0, -1),
            { ...last, status: 'cancelled', content: last.content + ' (Stopped)' },
          ];
        }
        return prev;
      });
    }
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const query = input.trim();
    if (!query || isStreaming || !selectedOrgId) return;

    setError(null);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    let convId = activeConversationId;

    // Auto-create conversation if none active
    if (!convId) {
      try {
        const newConvRes = await api.post(`/conversations?org_id=${selectedOrgId}`, {
          title: query.slice(0, 30),
        });
        const newConv = newConvRes.data;
        setConversations((prev) => [newConv, ...prev]);
        setActiveConversationId(newConv.id);
        convId = newConv.id;
      } catch (err) {
        console.error('Failed to auto-create conversation', err);
        setError('Failed to initiate conversation.');
        return;
      }
    }

    if (!convId) return;
    const finalConvId = convId as string;

    // Optimistic user message
    const tempUserMsg: Message = {
      id: 'temp-user-' + Date.now(),
      conversation_id: finalConvId,
      role: 'user',
      content: query,
      status: 'completed',
      created_at: new Date().toISOString(),
    };

    // Temporary assistant placeholder
    const tempAssistantMsg: Message = {
      id: 'temp-assistant-' + Date.now(),
      conversation_id: finalConvId,
      role: 'assistant',
      content: '',
      status: 'streaming',
      metadata: { sources: [] },
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, tempUserMsg, tempAssistantMsg]);
    setIsStreaming(true);
    setAgentStatus('Understanding query...');

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const token = localStorage.getItem('token');
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

    try {
      const response = await fetch(
        `${apiUrl}/conversations/${convId}/stream?org_id=${selectedOrgId}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ message: query }),
          signal: abortController.signal,
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Streaming failed');
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('ReadableStream not available');

      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let accumulatedText = '';
      let detectedSources: RAGSource[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = 'message';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.replace('event:', '').trim();
          } else if (trimmed.startsWith('data:')) {
            const dataStr = trimmed.replace('data:', '').trim();
            if (!dataStr) continue;

            try {
              const parsed = JSON.parse(dataStr);

              if (currentEvent === 'message_start') {
                if (parsed.title) {
                  setConversations((prev) =>
                    prev.map((c) =>
                      c.id === convId ? { ...c, title: parsed.title } : c
                    )
                  );
                }
              } else if (currentEvent === 'agent_intent') {
                if (parsed.intent === 'knowledge_question') {
                  setAgentStatus('Searching enterprise documents...');
                } else if (parsed.intent === 'conversational') {
                  setAgentStatus('Thinking...');
                } else if (parsed.intent === 'unsupported') {
                  setAgentStatus('Evaluating request...');
                }
              } else if (currentEvent === 'token') {
                setAgentStatus(null);
                if (parsed.text) {
                  accumulatedText += parsed.text;
                  setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant') {
                      return [
                        ...prev.slice(0, -1),
                        { ...last, content: accumulatedText },
                      ];
                    }
                    return prev;
                  });
                }
              } else if (currentEvent === 'citation') {
                if (parsed.sources) {
                  detectedSources = parsed.sources;
                  setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant') {
                      return [
                        ...prev.slice(0, -1),
                        { ...last, metadata: { ...last.metadata, sources: detectedSources } },
                      ];
                    }
                    return prev;
                  });
                }
              } else if (currentEvent === 'message_complete') {
                setAgentStatus(null);
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (last && last.role === 'assistant') {
                    return [
                      ...prev.slice(0, -1),
                      {
                        ...last,
                        status: 'completed',
                        content: accumulatedText,
                        metadata: { ...last.metadata, sources: detectedSources },
                      },
                    ];
                  }
                  return prev;
                });
              } else if (currentEvent === 'error') {
                setAgentStatus(null);
                setError(parsed.error || 'Generation error occurred.');
              }
            } catch (jsonErr) {
              console.warn('Failed to parse SSE JSON:', dataStr, jsonErr);
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Stream aborted by user');
      } else {
        console.error('Streaming request error:', err);
        setError(err.message || 'Error streaming response.');
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === 'assistant') {
            return [
              ...prev.slice(0, -1),
              {
                ...last,
                status: 'failed',
                content: last.content || 'An error occurred during response generation.',
              },
            ];
          }
          return prev;
        });
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const copyToClipboard = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const filteredConversations = conversations.filter((c) =>
    (c.title || 'Untitled Conversation')
      .toLowerCase()
      .includes(searchQuery.toLowerCase())
  );

  const activeConversation = conversations.find((c) => c.id === activeConversationId);

  return (
    <div className="flex h-[calc(100vh-5rem)] overflow-hidden bg-slate-50 border border-slate-200 rounded-xl shadow-sm">
      {/* Left Sidebar: Conversation History */}
      <div className="w-72 sm:w-80 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col">
        {/* Sidebar Header */}
        <div className="p-3 border-b border-slate-100 flex flex-col gap-2">
          <button
            onClick={handleCreateNewChat}
            disabled={isStreaming || !selectedOrgId}
            className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-medium text-sm rounded-lg shadow-sm transition-all"
          >
            <Plus className="h-4 w-4" />
            <span>New Chat</span>
          </button>

          {/* Search Filter */}
          <div className="relative mt-1">
            <Search className="h-3.5 w-3.5 absolute left-2.5 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-md text-xs text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingConversations ? (
            <div className="py-8 text-center text-xs text-slate-400">Loading chats...</div>
          ) : filteredConversations.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">
              {searchQuery ? 'No chats match filter.' : 'No conversations yet.'}
            </div>
          ) : (
            filteredConversations.map((conv) => {
              const isActive = conv.id === activeConversationId;
              const isEditing = editingTitleId === conv.id;

              return (
                <div
                  key={conv.id}
                  onClick={() => {
                    if (!isStreaming && !isEditing) setActiveConversationId(conv.id);
                  }}
                  className={`group relative flex items-center justify-between px-3 py-2.5 rounded-lg text-xs cursor-pointer transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-900 font-medium'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0 flex-1 pr-2">
                    <MessageSquare
                      className={`h-4 w-4 flex-shrink-0 ${
                        isActive ? 'text-indigo-600' : 'text-slate-400'
                      }`}
                    />
                    {isEditing ? (
                      <input
                        type="text"
                        value={editTitleText}
                        onChange={(e) => setEditTitleText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveTitle(conv.id);
                          if (e.key === 'Escape') setEditingTitleId(null);
                        }}
                        autoFocus
                        onClick={(e) => e.stopPropagation()}
                        className="w-full bg-white border border-indigo-300 rounded px-1.5 py-0.5 text-xs text-slate-900 focus:outline-none"
                      />
                    ) : (
                      <span className="truncate">{conv.title || 'Untitled Conversation'}</span>
                    )}
                  </div>

                  {/* Action buttons on hover */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {isEditing ? (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSaveTitle(conv.id);
                          }}
                          className="p-1 hover:text-green-600 text-slate-400"
                        >
                          <Check className="h-3 w-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingTitleId(null);
                          }}
                          className="p-1 hover:text-red-600 text-slate-400"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingTitleId(conv.id);
                            setEditTitleText(conv.title || '');
                          }}
                          className="p-1 hover:text-slate-700 text-slate-400"
                          title="Rename"
                        >
                          <Edit2 className="h-3 w-3" />
                        </button>
                        <button
                          onClick={(e) => handleDeleteConversation(e, conv.id)}
                          className="p-1 hover:text-red-600 text-slate-400"
                          title="Delete"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Right Main Chat Area */}
      <div className="flex-1 flex flex-col bg-white overflow-hidden">
        {/* Chat Top Bar */}
        <div className="h-14 border-b border-slate-200 px-4 flex items-center justify-between bg-white flex-shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-8 w-8 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600 flex-shrink-0">
              <Bot className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-slate-900 truncate">
                {activeConversation?.title || 'Knowledge Assistant'}
              </h2>
              <p className="text-[11px] text-slate-500 truncate">
                Phase 7 Real-Time Streaming RAG
              </p>
            </div>
          </div>

          {/* Org Selector */}
          <div className="flex items-center gap-2">
            <Building2 className="h-4 w-4 text-slate-400" />
            <select
              value={selectedOrgId}
              onChange={(e) => handleOrgChange(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-md px-2 py-1 text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              {organizations.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Messages Thread */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
          {error && (
            <div className="rounded-lg bg-red-50 p-3 border border-red-200 text-xs text-red-700 flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {loadingMessages ? (
            <div className="flex justify-center items-center h-48 text-xs text-slate-400">
              Loading conversation messages...
            </div>
          ) : messages.length === 0 ? (
            /* Empty State */
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto py-12">
              <div className="h-12 w-12 rounded-2xl bg-indigo-50 flex items-center justify-center text-indigo-600 mb-4 shadow-sm">
                <Sparkles className="h-6 w-6" />
              </div>
              <h3 className="text-base font-semibold text-slate-900">
                Enterprise Knowledge Chat
              </h3>
              <p className="text-xs text-slate-500 mt-1 mb-6">
                Ask questions to search your organization&apos;s indexed documents, policies, and pgvector embeddings with verified citations.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full text-left">
                {[
                  'What is our remote work allowance?',
                  'Summarize our annual leave policy.',
                  'When do performance reviews take place?',
                  'What are our expense reimbursement guidelines?',
                ].map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setInput(suggestion);
                      if (textareaRef.current) textareaRef.current.focus();
                    }}
                    className="p-2.5 text-xs text-slate-600 bg-slate-50 hover:bg-indigo-50/50 hover:text-indigo-700 border border-slate-200/80 rounded-lg transition-colors text-left"
                  >
                    &ldquo;{suggestion}&rdquo;
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Message Bubbles */
            messages.map((msg, index) => {
              const isUser = msg.role === 'user';
              const sources = msg.metadata?.sources || [];
              const isSourcesExpanded = !!expandedSources[msg.id];

              return (
                <div
                  key={msg.id || index}
                  className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {!isUser && (
                    <div className="h-7 w-7 rounded-lg bg-indigo-600 text-white flex items-center justify-center flex-shrink-0 text-xs shadow-sm mt-0.5">
                      <Bot className="h-3.5 w-3.5" />
                    </div>
                  )}

                  <div
                    className={`max-w-2xl rounded-2xl px-4 py-3 text-xs leading-relaxed shadow-sm ${
                      isUser
                        ? 'bg-indigo-600 text-white rounded-br-sm'
                        : 'bg-slate-50 text-slate-800 border border-slate-200/70 rounded-bl-sm'
                    }`}
                  >
                    {/* Message Content */}
                    {msg.status === 'streaming' && !msg.content && agentStatus ? (
                      <div className="flex items-center gap-2 text-slate-500 py-1 font-sans">
                        <Sparkles className="h-3.5 w-3.5 text-indigo-500 animate-spin" />
                        <span className="animate-pulse text-indigo-700 font-medium">{agentStatus}</span>
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap font-sans">
                        {msg.content}
                        {msg.status === 'streaming' && (
                          <span className="inline-block w-1.5 h-3.5 bg-indigo-500 ml-1 animate-pulse align-middle" />
                        )}
                      </div>
                    )}

                    {/* Citations / Sources for Assistant Responses */}
                    {!isUser && sources.length > 0 && (
                      <div className="mt-3 pt-2.5 border-t border-slate-200/60">
                        <button
                          onClick={() =>
                            setExpandedSources((prev) => ({
                              ...prev,
                              [msg.id]: !prev[msg.id],
                            }))
                          }
                          className="flex items-center gap-1.5 text-[11px] font-medium text-indigo-700 hover:text-indigo-800"
                        >
                          <FileText className="h-3 w-3" />
                          <span>
                            {sources.length} Grounded Citation
                            {sources.length > 1 ? 's' : ''}
                          </span>
                          {isSourcesExpanded ? (
                            <ChevronUp className="h-3 w-3" />
                          ) : (
                            <ChevronDown className="h-3 w-3" />
                          )}
                        </button>

                        {isSourcesExpanded && (
                          <div className="mt-2 space-y-1.5">
                            {sources.map((src, srcIdx) => (
                              <div
                                key={src.chunk_id || srcIdx}
                                className="p-2 bg-white border border-slate-200 rounded-md text-[11px] text-slate-700"
                              >
                                <div className="flex items-center justify-between font-medium text-slate-900 mb-1">
                                  <span className="truncate">{src.filename}</span>
                                  <span className="text-[10px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded font-mono">
                                    score: {(src.score || 0).toFixed(2)}
                                  </span>
                                </div>
                                <p className="text-slate-500 line-clamp-2 italic">
                                  &ldquo;{src.content_snippet}&rdquo;
                                </p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Copy Button for Assistant */}
                    {!isUser && msg.content && msg.status !== 'streaming' && (
                      <div className="mt-2 flex justify-end">
                        <button
                          onClick={() => copyToClipboard(msg.content, index)}
                          className="text-[10px] text-slate-400 hover:text-slate-600 flex items-center gap-1 transition-colors"
                        >
                          {copiedIndex === index ? (
                            <>
                              <CheckCheck className="h-3 w-3 text-green-600" />
                              <span className="text-green-600">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3 w-3" />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-3 sm:p-4 border-t border-slate-200 bg-white">
          <form
            onSubmit={handleSendMessage}
            className="relative flex items-end gap-2 bg-slate-50 border border-slate-200 rounded-xl p-2 focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-500 transition-all"
          >
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px';
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              placeholder={
                isStreaming
                  ? 'Generating response...'
                  : 'Ask a question based on your documents (Enter to send, Shift+Enter for new line)...'
              }
              disabled={isStreaming || !selectedOrgId}
              className="flex-1 bg-transparent resize-none text-xs text-slate-800 placeholder-slate-400 focus:outline-none max-h-36 py-1.5 px-2"
            />

            <div className="flex items-center gap-1.5 flex-shrink-0">
              {isStreaming ? (
                <button
                  type="button"
                  onClick={handleStopGeneration}
                  className="p-2 rounded-lg bg-red-600 hover:bg-red-700 text-white transition-colors shadow-sm"
                  title="Stop generating"
                >
                  <Square className="h-4 w-4 fill-current" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim() || !selectedOrgId}
                  className="p-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white transition-colors shadow-sm"
                  title="Send message"
                >
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>
          </form>
          <div className="mt-1.5 text-center">
            <span className="text-[10px] text-slate-400">
              Enterprise AI Assistant uses pgvector hybrid search and strict document grounding.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
