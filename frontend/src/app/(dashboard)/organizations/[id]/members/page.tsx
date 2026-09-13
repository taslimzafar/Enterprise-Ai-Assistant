"use client";

import { useEffect, useState, use } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { Users, Shield, User as UserIcon, Trash2, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { Role } from "@/types";

interface MemberWithUser {
  id: string;
  user_id: string;
  role: Role;
  email: string;
  full_name: string | null;
  created_at: string;
}

export default function MembersPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const orgId = resolvedParams.id;
  const { user, activeOrganization } = useAuth();
  
  const [members, setMembers] = useState<MemberWithUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  
  const [isAdding, setIsAdding] = useState(false);
  const [newMemberEmail, setNewMemberEmail] = useState("");
  const [newMemberRole, setNewMemberRole] = useState<Role>("MEMBER");
  const [addLoading, setAddLoading] = useState(false);

  // We find if current user is owner/admin
  const currentUserMember = members.find(m => m.user_id === user?.id);
  const canManage = currentUserMember?.role === "OWNER" || currentUserMember?.role === "ADMIN";

  const fetchMembers = async () => {
    try {
      setLoading(true);
      const res = await api.get(`/organizations/${orgId}/members`);
      setMembers(res.data);
    } catch (err) {
      setError("Failed to load members.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMembers();
  }, [orgId]);

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddLoading(true);
    
    // Using email instead of user_id now for better UX
    try {
      await api.post(`/organizations/${orgId}/members`, { 
        email: newMemberEmail,
        role: newMemberRole 
      });
      await fetchMembers();
      setIsAdding(false);
      setNewMemberEmail("");
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to add member.");
    } finally {
      setAddLoading(false);
    }
  };

  const handleRemove = async (userId: string) => {
    if (!confirm("Are you sure you want to remove this member?")) return;
    try {
      await api.delete(`/organizations/${orgId}/members/${userId}`);
      await fetchMembers();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to remove member");
    }
  };

  if (loading) return <div className="p-6">Loading members...</div>;
  if (error) return <div className="p-6 text-red-600">{error}</div>;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-4 border-b border-slate-200 pb-5">
        <Link href="/organizations" className="p-2 hover:bg-slate-100 rounded-full">
          <ArrowLeft className="h-5 w-5 text-slate-500" />
        </Link>
        <h1 className="text-2xl font-semibold text-slate-900">Manage Members</h1>
        
        {canManage && (
          <button
            onClick={() => setIsAdding(!isAdding)}
            className="ml-auto flex items-center justify-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
          >
            Add Member
          </button>
        )}
      </div>

      {isAdding && canManage && (
        <div className="bg-white shadow sm:rounded-lg p-6 mb-6">
          <h3 className="text-sm font-medium mb-4">Add a new member to this organization</h3>
          <form onSubmit={handleAddMember} className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="block text-sm font-medium leading-6 text-slate-900">
                User Email
              </label>
              <input
                type="email"
                required
                value={newMemberEmail}
                onChange={(e) => setNewMemberEmail(e.target.value)}
                className="mt-2 block w-full rounded-md border-0 py-1.5 px-3 text-slate-900 shadow-sm ring-1 ring-inset ring-slate-300"
                placeholder="user@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium leading-6 text-slate-900">
                Role
              </label>
              <select
                value={newMemberRole}
                onChange={(e) => setNewMemberRole(e.target.value as Role)}
                className="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-slate-900 shadow-sm ring-1 ring-inset ring-slate-300 sm:text-sm sm:leading-6"
              >
                <option value="MEMBER">Member</option>
                <option value="MANAGER">Manager</option>
                <option value="ADMIN">Admin</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={addLoading}
              className="rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-700 disabled:opacity-50 h-9"
            >
              {addLoading ? "Adding..." : "Add"}
            </button>
          </form>
        </div>
      )}

      <div className="overflow-hidden bg-white shadow sm:rounded-md">
        <ul role="list" className="divide-y divide-slate-200">
          {members.map((member) => (
            <li key={member.id}>
              <div className="flex items-center px-4 py-4 sm:px-6">
                <div className="min-w-0 flex-1 sm:flex sm:items-center sm:justify-between">
                  <div className="truncate">
                    <div className="flex text-sm">
                      <p className="truncate font-medium text-indigo-600">{member.full_name || member.email}</p>
                      <p className="ml-1 shrink-0 font-normal text-slate-500">
                        {member.full_name ? `(${member.email})` : ''}
                      </p>
                    </div>
                    <div className="mt-2 flex">
                      <div className="flex items-center text-sm text-slate-500">
                        <UserIcon className="mr-1.5 h-4 w-4 shrink-0 text-slate-400" />
                        <p>Joined {new Date(member.created_at).toLocaleDateString()}</p>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 flex shrink-0 sm:ml-5 sm:mt-0 items-center gap-4">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-slate-400" />
                      <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-800">
                        {member.role}
                      </span>
                    </div>
                    
                    {canManage && member.role !== 'OWNER' && member.user_id !== user?.id && (
                      <button 
                        onClick={() => handleRemove(member.user_id)}
                        className="text-red-500 hover:text-red-700 p-2 hover:bg-red-50 rounded-md"
                        title="Remove member"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
