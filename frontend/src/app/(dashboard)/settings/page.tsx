"use client";

import { useAuth } from "@/context/AuthContext";
import { User, Shield } from "lucide-react";

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between border-b border-slate-200 pb-5">
        <h1 className="text-2xl font-semibold text-slate-900">Settings</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <div className="md:col-span-1">
          <h3 className="text-lg font-medium leading-6 text-slate-900">Profile</h3>
          <p className="mt-1 text-sm text-slate-500">
            This information will be displayed publicly so be careful what you share.
          </p>
        </div>
        <div className="md:col-span-2">
          <div className="bg-white shadow sm:rounded-lg">
            <div className="px-4 py-5 sm:p-6 space-y-6">
              
              <div>
                <label className="block text-sm font-medium leading-6 text-slate-900">
                  Full Name
                </label>
                <div className="mt-2 flex rounded-md shadow-sm ring-1 ring-inset ring-slate-300 bg-slate-50">
                  <span className="flex select-none items-center pl-3 text-slate-500 sm:text-sm">
                    <User className="h-4 w-4 mr-2" />
                  </span>
                  <input
                    type="text"
                    disabled
                    value={user?.full_name || ''}
                    className="block flex-1 border-0 bg-transparent py-1.5 pl-1 text-slate-900 placeholder:text-slate-400 focus:ring-0 sm:text-sm sm:leading-6 cursor-not-allowed"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium leading-6 text-slate-900">
                  Email Address
                </label>
                <div className="mt-2">
                  <input
                    type="email"
                    disabled
                    value={user?.email || ''}
                    className="block w-full rounded-md border-0 py-1.5 text-slate-900 shadow-sm ring-1 ring-inset ring-slate-300 bg-slate-50 sm:text-sm sm:leading-6 px-3 cursor-not-allowed"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium leading-6 text-slate-900">
                  Account Status
                </label>
                <div className="mt-2 flex items-center">
                  {user?.is_active ? (
                    <span className="inline-flex items-center rounded-full bg-green-50 px-2 py-1 text-xs font-medium text-green-700 ring-1 ring-inset ring-green-600/20">
                      Active
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-1 text-xs font-medium text-red-700 ring-1 ring-inset ring-red-600/20">
                      Inactive
                    </span>
                  )}
                  {user?.is_superuser && (
                    <span className="ml-2 inline-flex items-center gap-x-1 rounded-full bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-600/20">
                      <Shield className="h-3 w-3" />
                      Superuser
                    </span>
                  )}
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
