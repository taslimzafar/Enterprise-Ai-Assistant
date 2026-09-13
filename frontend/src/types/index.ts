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

export type DocumentStatus = 'UPLOADED' | 'PROCESSING' | 'PROCESSED' | 'FAILED';

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
