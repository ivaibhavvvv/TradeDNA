"use client";

import React from "react";
import { Lock, Shield, UserX } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function SecurityPage() {
  const { user, logout } = useAuth();

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            SECURITY & ACTIVE SESSIONS
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            JWT session management, tenant boundary isolation, and cryptographic diagnostics.
          </p>
        </div>
        <Button
          variant="destructive"
          size="sm"
          onClick={logout}
          className="gap-2 text-xs"
        >
          <UserX className="h-3.5 w-3.5" />
          Terminate Current Session
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Active Session Card */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <Lock className="h-4 w-4 text-cyan-400" />
              Authenticated Session Identity
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Current cryptographic session token scope
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 font-mono text-xs">
            <div className="flex justify-between py-1.5 border-b border-slate-800">
              <span className="text-slate-400 font-sans">User Email:</span>
              <span className="text-slate-200">{user?.email}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800">
              <span className="text-slate-400 font-sans">Tenant ID:</span>
              <span className="text-cyan-400">{user?.tenant_id?.slice(0, 12)}...</span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-400 font-sans">Session Status:</span>
              <Badge variant="connected">Active JWT Bearer</Badge>
            </div>
          </CardContent>
        </Card>

        {/* Security Invariants Card */}
        <Card className="border-slate-800 bg-[#0d1321]">
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
              <Shield className="h-4 w-4 text-emerald-400" />
              TradeDNA Security Guarantees
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Strictly enforced platform boundaries
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-slate-300">
            <div className="flex items-start gap-2">
              <span className="text-emerald-400 font-bold">✓</span>
              <span><strong>Zero Broker Order Permissions:</strong> Connector is physically restricted from trade placement or modification.</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-emerald-400 font-bold">✓</span>
              <span><strong>Zero Client-Side Passwords:</strong> Exness MT5 account passwords are never accepted, transmitted, or stored.</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-emerald-400 font-bold">✓</span>
              <span><strong>Cryptographic HMAC Handshake:</strong> All Layer 1 ingress payloads are SHA256 signed.</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
