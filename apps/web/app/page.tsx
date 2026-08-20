import React from "react";
import Link from "next/link";
import {
  Activity,
  ShieldCheck,
  TrendingUp,
  Cpu,
  Layers,
  Sparkles,
  Lock,
  ArrowUpRight,
  Database,
  CheckCircle2,
  Dna,
} from "lucide-react";

export default function HomePage() {
  return (
    <div className="flex flex-col min-h-screen bg-[#070a11]">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-50 flex items-center justify-between px-6 py-4 border-b border-[#1b2333] bg-[#0a0e1a]/80 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 text-black font-mono font-bold text-xs shadow-lg shadow-cyan-500/20">
            DNA
          </div>
          <div>
            <span className="text-lg font-bold tracking-tight text-white font-mono">
              Trade<span className="text-cyan-400">DNA</span>
            </span>
            <span className="ml-2.5 px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase rounded-full bg-cyan-950/80 text-cyan-400 border border-cyan-800/50">
              Exness Exclusive
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="px-3.5 py-1.5 text-xs font-semibold text-slate-200 transition-colors rounded-lg hover:bg-slate-800 border border-slate-700/60"
          >
            Sign In
          </Link>
          <Link
            href="/register"
            className="px-3.5 py-1.5 text-xs font-semibold text-black transition-all rounded-lg bg-gradient-to-r from-cyan-400 to-cyan-500 hover:from-cyan-300 hover:to-cyan-400 shadow-md shadow-cyan-500/20"
          >
            Get Started
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-14">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 mb-6 rounded-full bg-cyan-950/50 border border-cyan-800/40 text-cyan-400 text-xs font-medium">
            <ShieldCheck className="w-4 h-4" />
            <span>Strictly Read-Only • Zero Order Placement • Full Decimal Precision</span>
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black text-white tracking-tight leading-[1.15]">
            Decode Your Trading. <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-teal-300 to-emerald-400">
              Understand Your Edge.
            </span>
          </h1>
          <p className="mt-5 text-sm sm:text-base text-slate-400 leading-relaxed">
            The dedicated quantitative intelligence platform for Exness MetaTrader 5 accounts.
            Transforms raw MT5 deal observations into deterministic financial ledgers, behavioral analytics,
            and your personal Trading DNA profile.
          </p>
          <div className="mt-8 flex justify-center gap-4">
            <Link
              href="/dashboard/overview"
              className="px-5 py-2.5 text-xs font-semibold text-black rounded-lg bg-cyan-400 hover:bg-cyan-300 transition-colors font-mono"
            >
              Open Dashboard Command Center →
            </Link>
          </div>
        </div>

        {/* Feature Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-16">
          <div className="p-6 rounded-xl bg-[#0f1523] border border-[#1b253b] hover:border-cyan-500/40 transition-all shadow-xl">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center text-cyan-400 mb-4 border border-cyan-500/20">
              <Database className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">Canonical Financial Ledger</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Mathematical reconciliation distinguishing Realized P&L, Commissions, Swaps, and Cash Balance using full Decimal precision.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-[#0f1523] border border-[#1b253b] hover:border-emerald-500/40 transition-all shadow-xl">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-400 mb-4 border border-emerald-500/20">
              <Dna className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">5-Axis Trading DNA</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Quantitative behavioral fingerprinting evaluating Consistency, Discipline, Execution Quality, Risk Management, and Profitability.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-[#0f1523] border border-[#1b253b] hover:border-purple-500/40 transition-all shadow-xl">
            <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center text-purple-400 mb-4 border border-purple-500/20">
              <Activity className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">10 Behavioral Anomaly Detectors</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Empirical pattern detection flagging Revenge Trading, Loss Escalation, and Overtrading Spikes with exact trade citations.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="mt-auto border-t border-[#161e30] py-6 px-6 text-center text-xs text-slate-500">
        <p>TradeDNA © 2026. Built exclusively for Exness MetaTrader 5 accounts. Strictly Read-Only & Informational.</p>
      </footer>
    </div>
  );
}
