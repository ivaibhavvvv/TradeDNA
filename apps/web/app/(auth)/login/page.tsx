"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Lock, Mail, AlertCircle } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("vaibhav251001@gmail.com");
  const [password, setPassword] = useState("TradeDNA@2026");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await login({ email, password });
    } catch (err: any) {
      setError(err?.message || "Invalid email or password");
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuickSignIn = async () => {
    setEmail("vaibhav251001@gmail.com");
    setPassword("TradeDNA@2026");
    setError(null);
    setIsLoading(true);
    try {
      await login({ email: "vaibhav251001@gmail.com", password: "TradeDNA@2026" });
    } catch (err: any) {
      setError(err?.message || "Quick sign-in failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="border-slate-800 bg-[#0d1321]/90 backdrop-blur-md shadow-2xl">
      <CardHeader className="space-y-1 pb-4">
        <CardTitle className="text-lg text-slate-100 font-semibold">Sign in to TradeDNA</CardTitle>
        <CardDescription className="text-xs text-slate-400">
          Enter your trader credentials to access your Exness intelligence dashboard.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="flex items-center gap-2 rounded-md border border-rose-900/50 bg-rose-950/40 p-2.5 text-xs text-rose-200">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Email Address</label>
            <div className="relative">
              <Mail className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <Input
                type="email"
                placeholder="trader@tradedna.io"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="pl-9 bg-slate-900/80 border-slate-700"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-slate-300">Password</label>
            </div>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <Input
                type="password"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="pl-9 bg-slate-900/80 border-slate-700"
              />
            </div>
          </div>

          <Button
            type="submit"
            variant="primary"
            className="w-full mt-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-black font-semibold shadow-lg shadow-cyan-500/20"
            disabled={isLoading}
          >
            {isLoading ? "Authenticating..." : "Sign In to Workspace"}
          </Button>

          <Button
            type="button"
            variant="outline"
            onClick={handleQuickSignIn}
            className="w-full border-cyan-500/40 hover:bg-cyan-950/40 text-cyan-400 text-xs font-mono"
            disabled={isLoading}
          >
            ⚡ 1-Click Quick Sign In (Vaibhav)
          </Button>

          <div className="mt-4 text-center text-xs text-slate-400">
            Don't have an account?{" "}
            <Link href="/register" className="text-cyan-400 hover:underline font-medium">
              Create workspace
            </Link>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
