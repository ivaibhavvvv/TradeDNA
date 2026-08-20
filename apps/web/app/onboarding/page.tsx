"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  ShieldCheck,
  Building2,
  Terminal,
  Key,
  RefreshCw,
  ArrowRight,
  Copy,
  Check,
  AlertCircle,
  Clock,
  Activity,
  Layers,
  Database,
  ExternalLink,
} from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { onboardingApi } from "@/lib/api-client";
import { OnboardingState, OnboardingSyncStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const STEPS = [
  { id: 1, label: "Verify Email", icon: ShieldCheck },
  { id: 2, label: "Workspace", icon: Building2 },
  { id: 3, label: "MT5 Connector", icon: Terminal },
  { id: 4, label: "Pair Account", icon: Key },
  { id: 5, label: "Historical Sync", icon: Activity },
  { id: 6, label: "Launch", icon: CheckCircle2 },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [currentStepIndex, setCurrentStepIndex] = useState(1);
  const [onboardingState, setOnboardingState] = useState<OnboardingState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Step 1: Email Verification
  const [verificationCode, setVerificationCode] = useState("");
  const [isVerifyingEmail, setIsVerifyingEmail] = useState(false);
  const [resendStatus, setResendStatus] = useState<string | null>(null);

  // Step 2: Workspace Settings
  const [workspaceName, setWorkspaceName] = useState("");
  const [defaultCurrency, setDefaultCurrency] = useState("USD");
  const [experienceLevel, setExperienceLevel] = useState("ADVANCED");
  const [isSavingWorkspace, setIsSavingWorkspace] = useState(false);

  // Step 4: Pairing Token
  const [pairingToken, setPairingToken] = useState<string | null>(null);
  const [tokenExpiresIn, setTokenExpiresIn] = useState(900);
  const [isGeneratingToken, setIsGeneratingToken] = useState(false);
  const [copied, setCopied] = useState(false);

  // Step 5: Live Sync Polling
  const [syncStatus, setSyncStatus] = useState<OnboardingSyncStatus | null>(null);
  const [isPollingSync, setIsPollingSync] = useState(false);

  // Load initial state
  useEffect(() => {
    async function loadState() {
      try {
        setIsLoading(true);
        const state = await onboardingApi.getState();
        setOnboardingState(state);
        if (state.workspace_name) setWorkspaceName(state.workspace_name);
        if (state.default_currency) setDefaultCurrency(state.default_currency);

        // Map backend step to UI step
        if (state.is_completed) {
          setCurrentStepIndex(6);
        } else if (state.current_step === "DATA_VALIDATED") {
          setCurrentStepIndex(6);
        } else if (state.current_step === "INITIAL_SYNC_IN_PROGRESS") {
          setCurrentStepIndex(5);
        } else if (state.current_step === "AWAITING_CONNECTOR_HANDSHAKE") {
          setCurrentStepIndex(4);
        } else if (state.current_step === "WORKSPACE_CONFIGURED") {
          setCurrentStepIndex(3);
        } else if (state.current_step === "EMAIL_VERIFIED") {
          setCurrentStepIndex(2);
        } else {
          setCurrentStepIndex(state.email_verified ? 2 : 1);
        }
      } catch (err: any) {
        setError(err?.message || "Failed to load onboarding status.");
      } finally {
        setIsLoading(false);
      }
    }
    loadState();
  }, []);

  // Timer countdown for pairing token
  useEffect(() => {
    if (!pairingToken || tokenExpiresIn <= 0) return;
    const timer = setInterval(() => {
      setTokenExpiresIn((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [pairingToken, tokenExpiresIn]);

  // Polling for live sync in Step 4/5
  useEffect(() => {
    if (currentStepIndex < 4 || currentStepIndex > 5) return;

    let interval: NodeJS.Timeout;
    const poll = async () => {
      try {
        setIsPollingSync(true);
        const status = await onboardingApi.getSyncStatus();
        setSyncStatus(status);

        if (status.is_validated) {
          setCurrentStepIndex(6);
        } else if (status.status === "SYNCING" || status.status === "CONNECTED") {
          setCurrentStepIndex(5);
        }
      } catch (err) {
        // Silently poll
      } finally {
        setIsPollingSync(false);
      }
    };

    poll();
    interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [currentStepIndex]);

  // Actions
  const handleVerifyEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsVerifyingEmail(true);
    try {
      const state = await onboardingApi.verifyEmail(verificationCode);
      setOnboardingState(state);
      setCurrentStepIndex(2);
    } catch (err: any) {
      setError(err?.message || "Invalid verification code. Use 789456 for instant testing.");
    } finally {
      setIsVerifyingEmail(false);
    }
  };

  const handleResendCode = async () => {
    setError(null);
    setResendStatus(null);
    try {
      const res = await onboardingApi.resendCode();
      setResendStatus(res.message);
    } catch (err: any) {
      setError(err?.message || "Failed to resend verification code.");
    }
  };

  const handleSaveWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSavingWorkspace(true);
    try {
      const state = await onboardingApi.configureWorkspace({
        workspace_name: workspaceName || "My Exness Portfolio",
        default_currency: defaultCurrency,
        experience_level: experienceLevel,
      });
      setOnboardingState(state);
      setCurrentStepIndex(3);
    } catch (err: any) {
      setError(err?.message || "Failed to save workspace settings.");
    } finally {
      setIsSavingWorkspace(false);
    }
  };

  const handleGeneratePairingToken = async () => {
    setError(null);
    setIsGeneratingToken(true);
    try {
      const res = await onboardingApi.initiatePairing({
        server_name: "Exness-Real25",
      });
      setPairingToken(res.pairing_token);
      setTokenExpiresIn(res.expires_in_seconds);
      setCurrentStepIndex(4);
    } catch (err: any) {
      setError(err?.message || "Failed to generate pairing token.");
    } finally {
      setIsGeneratingToken(false);
    }
  };

  const handleCopyToken = () => {
    if (!pairingToken) return;
    navigator.clipboard.writeText(pairingToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCompleteOnboarding = async () => {
    setError(null);
    try {
      const res = await onboardingApi.complete();
      router.push(res.redirect_url);
    } catch (err: any) {
      setError(err?.message || "Failed to complete onboarding.");
    }
  };

  const formatTime = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#080c14] flex items-center justify-center text-slate-400">
        <RefreshCw className="h-6 w-6 animate-spin text-emerald-500 mr-2" />
        Loading onboarding session...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-100 flex flex-col items-center justify-center p-4 py-8">
      {/* Top Brand Header */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/40 border border-emerald-800/40 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-2">
          <ShieldCheck className="h-3.5 w-3.5" />
          Production Onboarding Experience
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">TradeDNA Workspace Setup</h1>
        <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-lg mx-auto">
          Connect your Exness MT5 account in 100% read-only observation mode with automated double-entry verification.
        </p>
      </div>

      {/* Step Progress Tracker */}
      <div className="w-full max-w-3xl mb-8">
        <div className="grid grid-cols-6 gap-2">
          {STEPS.map((step) => {
            const Icon = step.icon;
            const isDone = currentStepIndex > step.id;
            const isCurrent = currentStepIndex === step.id;

            return (
              <div
                key={step.id}
                className={`flex flex-col items-center text-center p-2 rounded-lg border transition-all duration-200 ${
                  isDone
                    ? "border-emerald-700/60 bg-emerald-950/20 text-emerald-400"
                    : isCurrent
                    ? "border-cyan-500 bg-cyan-950/30 text-cyan-200 shadow-lg shadow-cyan-950/40"
                    : "border-slate-800/80 bg-slate-900/30 text-slate-500"
                }`}
              >
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mb-1.5 ${
                    isDone
                      ? "bg-emerald-600 text-white"
                      : isCurrent
                      ? "bg-cyan-500 text-slate-950 font-extrabold animate-pulse"
                      : "bg-slate-800 text-slate-400"
                  }`}
                >
                  {isDone ? <Check className="h-3.5 w-3.5" /> : step.id}
                </div>
                <span className="text-[11px] font-medium hidden sm:inline">{step.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Card Container */}
      <Card className="w-full max-w-2xl border-slate-800 bg-[#0d1321]/90 backdrop-blur-xl shadow-2xl">
        {error && (
          <div className="m-4 mb-0 flex items-center gap-2 rounded-md border border-rose-900/50 bg-rose-950/40 p-3 text-xs text-rose-200">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {/* STEP 1: Email Verification */}
        {currentStepIndex === 1 && (
          <>
            <CardHeader>
              <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-cyan-400" />
                Verify Your Work Email
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                A 6-digit confirmation PIN has been generated for your registered address.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleVerifyEmail} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-300">6-Digit Verification PIN</label>
                  <Input
                    type="text"
                    placeholder="Enter PIN (e.g. 789456)"
                    value={verificationCode}
                    onChange={(e) => setVerificationCode(e.target.value)}
                    className="border-slate-800 bg-slate-950/60 text-center text-lg font-mono tracking-widest text-emerald-400"
                    maxLength={6}
                    required
                  />
                  <p className="text-[11px] text-slate-500">Demo test codes: 789456, 123456</p>
                </div>

                {resendStatus && (
                  <p className="text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {resendStatus}
                  </p>
                )}

                <div className="flex items-center justify-between pt-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={handleResendCode}
                    className="text-xs text-slate-400 hover:text-white"
                  >
                    Resend Code
                  </Button>
                  <Button
                    type="submit"
                    disabled={isVerifyingEmail || verificationCode.length < 4}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-5"
                  >
                    {isVerifyingEmail ? "Verifying..." : "Verify & Continue"}
                    <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                  </Button>
                </div>
              </form>
            </CardContent>
          </>
        )}

        {/* STEP 2: Workspace Settings */}
        {currentStepIndex === 2 && (
          <>
            <CardHeader>
              <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                <Building2 className="h-5 w-5 text-cyan-400" />
                Configure Trading Workspace
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Personalize your tenant environment and default reporting currency.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveWorkspace} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-300">Workspace / Firm Name</label>
                  <Input
                    type="text"
                    placeholder="e.g. Apex Alpha Trading Desk"
                    value={workspaceName}
                    onChange={(e) => setWorkspaceName(e.target.value)}
                    className="border-slate-800 bg-slate-950/60 text-slate-100"
                    required
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-300">Base Currency</label>
                    <select
                      value={defaultCurrency}
                      onChange={(e) => setDefaultCurrency(e.target.value)}
                      className="w-full h-9 rounded-md border border-slate-800 bg-slate-950/60 px-3 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    >
                      <option value="USD">USD — US Dollar ($)</option>
                      <option value="EUR">EUR — Euro (€)</option>
                      <option value="GBP">GBP — British Pound (£)</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-300">Experience Profile</label>
                    <select
                      value={experienceLevel}
                      onChange={(e) => setExperienceLevel(e.target.value)}
                      className="w-full h-9 rounded-md border border-slate-800 bg-slate-950/60 px-3 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    >
                      <option value="INTERMEDIATE">Professional Trader</option>
                      <option value="ADVANCED">Prop Firm / Fund Manager</option>
                      <option value="RETAIL">Quantitative Analyst</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end pt-3">
                  <Button
                    type="submit"
                    disabled={isSavingWorkspace || !workspaceName}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-5"
                  >
                    {isSavingWorkspace ? "Saving..." : "Proceed to Connector Setup"}
                    <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                  </Button>
                </div>
              </form>
            </CardContent>
          </>
        )}

        {/* STEP 3: MT5 Connector Installation Guide */}
        {currentStepIndex === 3 && (
          <>
            <CardHeader>
              <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                <Terminal className="h-5 w-5 text-cyan-400" />
                Install Exness MT5 Read-Only Connector
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                TradeDNA strictly uses an observational MQL5 EA to transmit ledger events over HTTPS.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-xs">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3.5 space-y-2.5 text-slate-300">
                <div className="flex items-start gap-2.5">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-950 text-emerald-400 font-bold border border-emerald-800 text-[11px]">
                    1
                  </span>
                  <div>
                    <span className="font-semibold text-white">Download the EA File:</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Copy <code className="text-emerald-400">TradeDNAConnector.ex5</code> to your MetaTrader 5 folder:{" "}
                      <code className="text-slate-300">MQL5\Experts\</code>
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-950 text-emerald-400 font-bold border border-emerald-800 text-[11px]">
                    2
                  </span>
                  <div>
                    <span className="font-semibold text-white">Allow HTTPS WebRequest:</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      In MT5, open <strong>Tools → Options → Expert Advisors</strong>. Check &quot;Allow WebRequest for
                      listed URL&quot; and add: <code className="text-cyan-400">https://api.tradedna.io</code>
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-950 text-emerald-400 font-bold border border-emerald-800 text-[11px]">
                    3
                  </span>
                  <div>
                    <span className="font-semibold text-white">Safety Verification:</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Do <strong>NOT</strong> check &quot;Allow Automated Trading&quot;. TradeDNA operates with zero
                      execution permissions.
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  onClick={handleGeneratePairingToken}
                  disabled={isGeneratingToken}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-5"
                >
                  {isGeneratingToken ? "Generating Pairing Key..." : "Generate Pairing Key"}
                  <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </>
        )}

        {/* STEP 4: Pairing Token & Handshake Awaiting */}
        {currentStepIndex === 4 && (
          <>
            <CardHeader>
              <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                <Key className="h-5 w-5 text-emerald-400" />
                Pair Your Exness Terminal
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Attach TradeDNAConnector to any chart in MT5 and input this single-use pairing key.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">Single-Use Pairing Token:</span>
                  <span className="text-xs font-mono text-amber-400 flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    Expires in {formatTime(tokenExpiresIn)}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <Input
                    readOnly
                    value={pairingToken || "Loading token..."}
                    className="border-slate-800 bg-slate-900/80 font-mono text-xs text-emerald-400"
                  />
                  <Button
                    type="button"
                    onClick={handleCopyToken}
                    className="bg-slate-800 hover:bg-slate-700 text-white shrink-0"
                    size="sm"
                  >
                    {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              <div className="rounded-lg border border-cyan-900/30 bg-cyan-950/20 p-3.5 flex items-center gap-3 text-xs text-cyan-200">
                <RefreshCw className="h-4 w-4 animate-spin text-cyan-400 shrink-0" />
                <span>
                  Listening for incoming MT5 terminal handshake... Attach the EA to an MT5 chart to complete pairing.
                </span>
              </div>

              <div className="flex justify-between items-center pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleGeneratePairingToken}
                  className="text-xs text-slate-400"
                >
                  Regenerate Key
                </Button>
                <Button
                  type="button"
                  onClick={() => setCurrentStepIndex(5)}
                  className="bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
                >
                  Next Step
                  <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </>
        )}

        {/* STEP 5: Live Historical Syncing & Validation */}
        {currentStepIndex === 5 && (
          <>
            <CardHeader>
              <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                <Activity className="h-5 w-5 text-cyan-400" />
                Historical Ingestion & Data Validation
              </CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Reconstructing double-entry ledger from Layer 1 raw Exness deals.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-xs">
              <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950/40 p-4">
                <div className="flex justify-between items-center text-slate-300">
                  <span>Connected Account:</span>
                  <span className="font-mono text-emerald-400 font-semibold">
                    {syncStatus?.account_number ? `Exness #${syncStatus.account_number}` : "Detecting Account..."}
                  </span>
                </div>
                <div className="flex justify-between items-center text-slate-300">
                  <span>Deals Ingested:</span>
                  <span className="font-mono text-white">{syncStatus?.deals_ingested ?? 0} events</span>
                </div>
                <div className="flex justify-between items-center text-slate-300">
                  <span>Double-Entry Balance:</span>
                  <span className="font-mono text-emerald-400">
                    {syncStatus?.balance ? `$${syncStatus.balance}` : "Calculating..."}
                  </span>
                </div>
                <div className="flex justify-between items-center text-slate-300">
                  <span>Data Integrity Grade:</span>
                  <span className="font-mono text-amber-300 font-bold">
                    {syncStatus?.integrity_grade || "Grade Pending"} (
                    {syncStatus?.integrity_score ? `${syncStatus.integrity_score}%` : "Calculating"}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 text-cyan-300 text-xs animate-pulse">
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                <span>{syncStatus?.details || "Performing initial canonical reconstruction..."}</span>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  onClick={() => setCurrentStepIndex(6)}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-5"
                >
                  View Launch Summary
                  <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </>
        )}

        {/* STEP 6: Launch Ready */}
        {currentStepIndex === 6 && (
          <>
            <CardHeader className="text-center pb-2">
              <div className="w-12 h-12 rounded-full bg-emerald-950/80 border border-emerald-500/50 flex items-center justify-center mx-auto mb-2 text-emerald-400">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <CardTitle className="text-xl text-white font-bold">Your Workspace is Ready</CardTitle>
              <CardDescription className="text-xs text-slate-400">
                Exness account integration and double-entry financial truth have been established.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-2.5 rounded-lg border border-slate-800 bg-slate-950/60 p-3.5 text-slate-300">
                <div>
                  <span className="text-slate-500 text-[11px]">Workspace</span>
                  <p className="font-semibold text-white">{onboardingState?.workspace_name || "Exness Portfolio"}</p>
                </div>
                <div>
                  <span className="text-slate-500 text-[11px]">Mode</span>
                  <p className="font-semibold text-emerald-400">100% Read-Only</p>
                </div>
                <div>
                  <span className="text-slate-500 text-[11px]">Reporting Currency</span>
                  <p className="font-semibold text-white">{onboardingState?.default_currency || "USD"}</p>
                </div>
                <div>
                  <span className="text-slate-500 text-[11px]">Financial Drift</span>
                  <p className="font-semibold text-emerald-400">$0.00000000</p>
                </div>
              </div>

              <Button
                onClick={handleCompleteOnboarding}
                className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-2.5 text-xs shadow-lg shadow-emerald-950/50"
              >
                Enter TradeDNA Command Center
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
