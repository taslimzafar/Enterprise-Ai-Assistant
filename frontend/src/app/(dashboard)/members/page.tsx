"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

export default function MembersRedirect() {
  const router = useRouter();
  const { activeOrganization, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading) {
      if (activeOrganization) {
        router.replace(`/organizations/${activeOrganization.id}/members`);
      } else {
        router.replace('/organizations');
      }
    }
  }, [activeOrganization, isLoading, router]);

  return (
    <div className="flex h-full items-center justify-center p-6">
      <p className="text-slate-500">Redirecting to members...</p>
    </div>
  );
}
