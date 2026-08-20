"use client";

/**
 * TradeDNA Phase 8 - Protected Dashboard Shell Layout.
 * Enforces authentication, wraps query & account contexts, and manages layout grid.
 */

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AuthProvider, useAuth } from "@/components/providers/auth-provider";
import { QueryProvider } from "@/components/providers/query-provider";
import { AccountProvider } from "@/components/providers/account-provider";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";

function ProtectedDashboardGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#070a11]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
          <span className="text-xs font-mono text-slate-400">Loading TradeDNA Shell...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <AccountProvider>
      <div className="flex min-h-screen bg-[#070a11] text-slate-100 antialiased selection:bg-cyan-500 selection:text-black">
        {/* Desktop Sidebar Navigation */}
        <Sidebar />

        {/* Main Content Area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
            <div className="mx-auto max-w-7xl space-y-6">
              {children}
            </div>
          </main>
        </div>
      </div>
    </AccountProvider>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <ProtectedDashboardGuard>{children}</ProtectedDashboardGuard>;
}
