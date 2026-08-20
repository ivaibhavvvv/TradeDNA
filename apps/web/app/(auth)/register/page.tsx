"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Lock, Mail, User as UserIcon, Building2, AlertCircle } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function RegisterPage() {
  const { register } = useAuth();
  const [fullName, setFullName] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await register({
        full_name: fullName,
        tenant_name: tenantName || `${fullName}'s Workspace`,
        email,
        password,
      });
    } catch (err: any) {
      setError(err?.message || "Registration failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="border-slate-800 bg-[#0d1321]/90 backdrop-blur-md shadow-2xl">
      <CardHeader className="space-y-1 pb-4">
        <CardTitle className="text-lg text-slate-100 font-semibold">Create TradeDNA Workspace</CardTitle>
        <CardDescription className="text-xs text-slate-400">
          Provision your tenant workspace and pair your live Exness MT5 account.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3.5">
          {error && (
            <div className="flex items-center gap-2 rounded-md border border-rose-900/50 bg-rose-950/40 p-2.5 text-xs text-rose-200">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-300">Full Name</label>
            <div className="relative">
              <UserIcon className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <Input
                type="text"
                placeholder="Alex Morgan"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                className="pl-9 bg-slate-900/80 border-slate-700"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-300">Tenant / Workspace Name</label>
            <div className="relative">
              <Building2 className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <Input
                type="text"
                placeholder="Alpha Trading Desk"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                required
                className="pl-9 bg-slate-900/80 border-slate-700"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-300">Email Address</label>
            <div className="relative">
              <Mail className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <Input
                type="email"
                placeholder="alex@tradedna.io"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="pl-9 bg-slate-900/80 border-slate-700"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-300">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <Input
                type="password"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="pl-9 bg-slate-900/80 border-slate-700"
              />
            </div>
          </div>

          <Button
            type="submit"
            variant="primary"
            className="w-full mt-3"
            disabled={isLoading}
          >
            {isLoading ? "Provisioning..." : "Create Account & Workspace"}
          </Button>

          <div className="mt-4 text-center text-xs text-slate-400">
            Already have a workspace?{" "}
            <Link href="/login" className="text-cyan-400 hover:underline font-medium">
              Sign in
            </Link>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
