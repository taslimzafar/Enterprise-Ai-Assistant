"use client";

import { useEffect, useState, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import {
  FileText,
  Upload,
  Trash2,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  File as FileIcon,
  FileType,
} from "lucide-react";
import { Document as DocType, DocumentStatus } from "@/types";

const FILE_TYPE_LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "DOCX",
  txt: "TXT",
};

const STATUS_CONFIG: Record<
  DocumentStatus,
  { label: string; color: string; icon: typeof CheckCircle2 }
> = {
  UPLOADED: {
    label: "Uploaded",
    color: "bg-blue-100 text-blue-800",
    icon: Clock,
  },
  PROCESSING: {
    label: "Processing",
    color: "bg-yellow-100 text-yellow-800",
    icon: Loader2,
  },
  PROCESSED: {
    label: "Processed",
    color: "bg-green-100 text-green-800",
    icon: CheckCircle2,
  },
  FAILED: {
    label: "Failed",
    color: "bg-red-100 text-red-800",
    icon: XCircle,
  },
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const { activeOrganization } = useAuth();
  const orgId = activeOrganization?.id;

  const [documents, setDocuments] = useState<DocType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Determine if user can manage (OWNER/ADMIN role)
  // We'll derive this from the membership data
  const [userRole, setUserRole] = useState<string | null>(null);
  const canUpload =
    userRole === "OWNER" || userRole === "ADMIN" || userRole === "MANAGER";
  const canDelete = userRole === "OWNER" || userRole === "ADMIN";

  useEffect(() => {
    if (orgId) {
      fetchDocuments();
      fetchUserRole();
    }
  }, [orgId]);

  const fetchUserRole = async () => {
    if (!orgId) return;
    try {
      const res = await api.get(`/organizations/${orgId}/members`);
      const { user } = useAuth as any;
      // Get current user from auth context indirectly via /auth/me
      const meRes = await api.get("/auth/me");
      const currentUserId = meRes.data.id;
      const myMembership = res.data.find(
        (m: any) => m.user_id === currentUserId
      );
      if (myMembership) {
        setUserRole(myMembership.role);
      }
    } catch {
      // If role fetch fails, default to restricted
    }
  };

  const fetchDocuments = async () => {
    if (!orgId) return;
    try {
      setLoading(true);
      setError("");
      const res = await api.get(`/documents?org_id=${orgId}`);
      setDocuments(res.data);
    } catch {
      setError("Failed to load documents.");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !orgId) return;

    setUploading(true);
    setUploadError("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      await api.post(`/documents?org_id=${orgId}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await fetchDocuments();
    } catch (err: any) {
      setUploadError(
        err.response?.data?.detail || "Upload failed. Please try again."
      );
    } finally {
      setUploading(false);
      // Reset file input
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm("Are you sure you want to delete this document?")) return;
    if (!orgId) return;

    try {
      await api.delete(`/documents/${docId}?org_id=${orgId}`);
      await fetchDocuments();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to delete document.");
    }
  };

  if (!orgId) {
    return (
      <div className="flex h-[80vh] flex-col items-center justify-center text-center">
        <div className="rounded-full bg-slate-100 p-6">
          <FileText className="h-12 w-12 text-slate-400" />
        </div>
        <h2 className="mt-6 text-2xl font-semibold text-slate-900">
          No Organization Selected
        </h2>
        <p className="mt-2 text-slate-500 max-w-sm">
          Please select an organization to manage documents.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Documents</h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload and manage enterprise documents for your knowledge base.
          </p>
        </div>
        {canUpload && (
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={handleUpload}
              className="hidden"
              id="document-upload"
            />
            <label
              htmlFor="document-upload"
              className={`flex items-center justify-center rounded-md px-4 py-2 text-sm font-semibold text-white shadow-sm cursor-pointer ${
                uploading
                  ? "bg-indigo-400 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-500"
              }`}
            >
              {uploading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  Upload Document
                </>
              )}
            </label>
          </div>
        )}
      </div>

      {/* Upload Error */}
      {uploadError && (
        <div className="rounded-md bg-red-50 p-4">
          <div className="flex">
            <XCircle className="h-5 w-5 text-red-400" />
            <div className="ml-3">
              <p className="text-sm text-red-700">{uploadError}</p>
            </div>
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      )}

      {/* Error state */}
      {error && !loading && (
        <div className="rounded-md bg-red-50 p-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && documents.length === 0 && (
        <div className="flex h-[50vh] flex-col items-center justify-center text-center">
          <div className="rounded-full bg-slate-100 p-6">
            <FileText className="h-12 w-12 text-slate-400" />
          </div>
          <h2 className="mt-6 text-lg font-semibold text-slate-900">
            No documents yet
          </h2>
          <p className="mt-2 text-slate-500 max-w-sm">
            Upload PDF, DOCX, or TXT files to build your knowledge base.
          </p>
        </div>
      )}

      {/* Document list */}
      {!loading && documents.length > 0 && (
        <div className="overflow-hidden bg-white shadow sm:rounded-md">
          <ul role="list" className="divide-y divide-slate-200">
            {documents.map((doc) => {
              const statusCfg = STATUS_CONFIG[doc.status];
              const StatusIcon = statusCfg.icon;

              return (
                <li key={doc.id}>
                  <div className="flex items-center px-4 py-4 sm:px-6">
                    {/* File icon */}
                    <div className="flex-shrink-0 mr-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100">
                        <FileType className="h-5 w-5 text-slate-500" />
                      </div>
                    </div>

                    {/* File info */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <p className="truncate text-sm font-medium text-slate-900">
                          {doc.original_filename}
                        </p>
                        <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                          {FILE_TYPE_LABELS[doc.file_type] || doc.file_type.toUpperCase()}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center gap-4 text-xs text-slate-500">
                        <span>{formatFileSize(doc.file_size)}</span>
                        <span>
                          {new Date(doc.created_at).toLocaleDateString()}
                        </span>
                        {doc.status === "PROCESSED" && (
                          <span>{doc.chunk_count} chunks</span>
                        )}
                      </div>
                      {/* Processing error */}
                      {doc.status === "FAILED" && doc.processing_error && (
                        <p className="mt-1 text-xs text-red-600 truncate max-w-md">
                          Error: {doc.processing_error}
                        </p>
                      )}
                    </div>

                    {/* Status badge */}
                    <div className="flex items-center gap-3 ml-4">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${statusCfg.color}`}
                      >
                        <StatusIcon
                          className={`h-3.5 w-3.5 ${
                            doc.status === "PROCESSING" ? "animate-spin" : ""
                          }`}
                        />
                        {statusCfg.label}
                      </span>

                      {/* Delete button */}
                      {canDelete && (
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="text-red-500 hover:text-red-700 p-2 hover:bg-red-50 rounded-md"
                          title="Delete document"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
