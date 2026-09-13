"use client";

import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { Building2, Plus, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function OrganizationsPage() {
  const { organizations, fetchData } = useAuth();
  const [isCreating, setIsCreating] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [loading, setLoading] = useState(false);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newOrgName.trim()) return;
    
    setLoading(true);
    try {
      await api.post('/organizations/', { name: newOrgName });
      await fetchData(); // Refresh orgs
      setIsCreating(false);
      setNewOrgName("");
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Organizations</h1>
        <button
          onClick={() => setIsCreating(!isCreating)}
          className="flex items-center justify-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
        >
          <Plus className="h-4 w-4 mr-2" />
          New Organization
        </button>
      </div>

      {isCreating && (
        <div className="bg-white shadow sm:rounded-lg p-6 mb-6">
          <form onSubmit={handleCreate} className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="block text-sm font-medium leading-6 text-slate-900">
                Organization Name
              </label>
              <div className="mt-2">
                <input
                  type="text"
                  required
                  value={newOrgName}
                  onChange={(e) => setNewOrgName(e.target.value)}
                  className="block w-full rounded-md border-0 py-1.5 text-slate-900 shadow-sm ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6 px-3"
                  placeholder="Acme Corp"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-700 disabled:opacity-50 h-9"
            >
              {loading ? "Creating..." : "Create"}
            </button>
            <button
              type="button"
              onClick={() => setIsCreating(false)}
              className="rounded-md bg-white px-3 py-2 text-sm font-semibold text-slate-900 shadow-sm ring-1 ring-inset ring-slate-300 hover:bg-slate-50 h-9"
            >
              Cancel
            </button>
          </form>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {organizations.map((org) => (
          <div
            key={org.id}
            className="col-span-1 flex flex-col divide-y divide-slate-200 rounded-lg bg-white shadow transition-all hover:shadow-md"
          >
            <div className="flex flex-1 flex-col p-8">
              <div className="mx-auto flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100">
                <Building2 className="h-8 w-8 text-indigo-600" />
              </div>
              <h3 className="mt-6 text-center text-sm font-medium text-slate-900">{org.name}</h3>
              <dl className="mt-1 flex flex-grow flex-col justify-between text-center">
                <dt className="sr-only">Slug</dt>
                <dd className="text-sm text-slate-500">{org.slug}</dd>
                <dt className="sr-only">Created</dt>
                <dd className="mt-3">
                  <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-800">
                    {new Date(org.created_at).toLocaleDateString()}
                  </span>
                </dd>
              </dl>
            </div>
            <div>
              <div className="-mt-px flex divide-x divide-slate-200">
                <div className="flex w-0 flex-1">
                  <Link
                    href={`/organizations/${org.id}/members`}
                    className="relative -mr-px inline-flex w-0 flex-1 items-center justify-center gap-x-3 rounded-bl-lg border-transparent py-4 text-sm font-semibold text-slate-900 hover:bg-slate-50"
                  >
                    Manage Members
                    <ArrowRight className="h-4 w-4 text-slate-400" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
