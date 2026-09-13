export type Role = 'OWNER' | 'ADMIN' | 'MANAGER' | 'MEMBER';

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface Membership {
  id: string;
  user_id: string;
  organization_id: string;
  role: Role;
  created_at: string;
}

export type DocumentStatus = 'UPLOADED' | 'PROCESSING' | 'EMBEDDING' | 'PROCESSED' | 'FAILED';

export interface Document {
  id: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  processing_error: string | null;
  chunk_count: number;
  created_at: string;
  processed_at: string | null;
}

export interface RAGSource {
  document_id: string;
  chunk_id: string;
  filename: string;
  page: number | null;
  chunk_index: number;
  score: number;
  content_snippet?: string;
}

export interface RAGQueryResponse {
  answer: string;
  sources: RAGSource[];
}

export type MessageRole = 'user' | 'assistant' | 'system';
export type MessageStatus = 'pending' | 'streaming' | 'completed' | 'failed' | 'cancelled';

export interface Message {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  metadata?: {
    sources?: RAGSource[];
    error?: string;
    cancelled?: boolean;
    [key: string]: any;
  } | null;
  created_at: string;
  updated_at?: string | null;
}

export interface Conversation {
  id: string;
  organization_id: string;
  user_id: string | null;
  title: string | null;
  created_at: string;
  updated_at?: string | null;
}
