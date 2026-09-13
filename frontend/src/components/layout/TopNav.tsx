"use client";

import { useAuth } from '@/context/AuthContext';
import { LogOut, User as UserIcon } from 'lucide-react';
import Link from 'next/link';

export default function TopNav() {
  const { user, activeOrganization, organizations, setActiveOrganization, logout } = useAuth();

  if (!user) return null;

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center space-x-4">
        {/* Organization Selector */}
        {organizations.length > 0 && (
          <select 
            className="block w-48 rounded-md border-slate-300 py-1.5 pl-3 pr-10 text-sm focus:border-indigo-500 focus:outline-none focus:ring-indigo-500 sm:text-sm bg-slate-50 border shadow-sm"
            value={activeOrganization?.id || ''}
            onChange={(e) => {
              const org = organizations.find(o => o.id === e.target.value);
              if (org) setActiveOrganization(org);
            }}
          >
            {organizations.map(org => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="flex items-center space-x-4">
        <span className="text-sm text-slate-700 font-medium">
          {user.full_name || user.email}
        </span>
        
        <div className="relative flex items-center gap-2 border-l pl-4 border-slate-200">
          <Link href="/settings" className="p-1 text-slate-400 hover:text-slate-600 rounded-full hover:bg-slate-100">
             <UserIcon className="h-5 w-5" />
          </Link>
          <button 
            onClick={() => logout()}
            className="p-1 text-slate-400 hover:text-red-600 rounded-full hover:bg-slate-100"
            title="Log out"
          >
            <LogOut className="h-5 w-5" />
          </button>
        </div>
      </div>
    </header>
  );
}
