import React from "react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#070a11] p-4 text-slate-100 antialiased selection:bg-cyan-500 selection:text-black">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-1.5">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 font-mono font-bold text-black text-base shadow-lg shadow-cyan-500/20 mb-2">
            DNA
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white font-mono">
            TRADEDNA
          </h1>
          <p className="text-xs text-slate-400 tracking-wide">
            Exness-Exclusive Financial Intelligence & Behavioral Analytics
          </p>
        </div>
        {children}
        <div className="text-center text-[11px] text-slate-500">
          Strictly Read-Only • 0 Broker Execution Permissions
        </div>
      </div>
    </div>
  );
}
