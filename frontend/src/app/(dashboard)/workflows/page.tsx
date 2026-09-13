import { Workflow } from "lucide-react";

export default function WorkflowsPage() {
  return (
    <div className="flex h-[80vh] flex-col items-center justify-center text-center">
      <div className="rounded-full bg-slate-100 p-6">
        <Workflow className="h-12 w-12 text-slate-400" />
      </div>
      <h2 className="mt-6 text-2xl font-semibold text-slate-900">Automated Workflows</h2>
      <p className="mt-2 text-slate-500 max-w-sm">
        Design and execute multi-step agentic workflows and tool integrations.
      </p>
      <div className="mt-8">
        <button className="rounded-md bg-indigo-600 px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 opacity-50 cursor-not-allowed">
          Coming Soon
        </button>
      </div>
    </div>
  );
}
