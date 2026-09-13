"use client";

import { useAuth } from "@/context/AuthContext";
import { Users, FileText, Bot, Activity } from "lucide-react";

export default function DashboardPage() {
  const { user, activeOrganization } = useAuth();

  const stats = [
    { name: 'Active Members', value: '12', icon: Users, change: '+2.1%', changeType: 'positive' },
    { name: 'Documents Indexed', value: '1,244', icon: FileText, change: '+14.5%', changeType: 'positive' },
    { name: 'AI Queries Today', value: '423', icon: Bot, change: '-4.1%', changeType: 'negative' },
    { name: 'Workflows Executed', value: '89', icon: Activity, change: '+12.3%', changeType: 'positive' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">
          Welcome back, {user?.full_name || user?.email}
        </h1>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.name}
            className="overflow-hidden rounded-lg bg-white px-4 py-5 shadow sm:p-6"
          >
            <div className="flex items-center">
              <div className="flex-shrink-0 rounded-md bg-indigo-50 p-3">
                <stat.icon className="h-6 w-6 text-indigo-600" aria-hidden="true" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="truncate text-sm font-medium text-slate-500">{stat.name}</dt>
                  <dd>
                    <div className="text-lg font-medium text-slate-900">{stat.value}</div>
                  </dd>
                </dl>
              </div>
            </div>
            <div className="mt-4">
              <span className={`text-sm font-medium ${stat.changeType === 'positive' ? 'text-green-600' : 'text-red-600'}`}>
                {stat.change}
              </span>
              <span className="text-sm text-slate-500 ml-2">from last week</span>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-8 rounded-lg bg-white shadow">
        <div className="border-b border-slate-200 px-4 py-5 sm:px-6 flex justify-between items-center">
          <h3 className="text-base font-semibold leading-6 text-slate-900">Recent Activity</h3>
        </div>
        <ul role="list" className="divide-y divide-slate-200">
          <li className="px-4 py-4 sm:px-6">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-indigo-600 truncate">Q3 Financial Report Summary generated</p>
              <div className="ml-2 flex flex-shrink-0">
                <p className="inline-flex rounded-full bg-green-100 px-2 text-xs font-semibold leading-5 text-green-800">
                  Completed
                </p>
              </div>
            </div>
            <div className="mt-2 sm:flex sm:justify-between">
              <div className="sm:flex">
                <p className="flex items-center text-sm text-slate-500">
                  AI Assistant
                </p>
              </div>
              <div className="mt-2 flex items-center text-sm text-slate-500 sm:mt-0">
                <p>2 minutes ago</p>
              </div>
            </div>
          </li>
          <li className="px-4 py-4 sm:px-6">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-indigo-600 truncate">New member invited to {activeOrganization?.name}</p>
              <div className="ml-2 flex flex-shrink-0">
                <p className="inline-flex rounded-full bg-blue-100 px-2 text-xs font-semibold leading-5 text-blue-800">
                  Pending
                </p>
              </div>
            </div>
            <div className="mt-2 sm:flex sm:justify-between">
              <div className="sm:flex">
                <p className="flex items-center text-sm text-slate-500">
                  System
                </p>
              </div>
              <div className="mt-2 flex items-center text-sm text-slate-500 sm:mt-0">
                <p>1 hour ago</p>
              </div>
            </div>
          </li>
        </ul>
      </div>
    </div>
  );
}
