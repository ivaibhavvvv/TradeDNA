"use client";

/**
 * TradeDNA Phase 8 - Authentication Context & Route Guard.
 * Manages user identity, tokens, session expiration, and login/logout flows.
 */

import React, { createContext, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  authApi,
  clearStoredAuth,
  getStoredToken,
  getStoredUser,
} from "@/lib/api-client";
import { User } from "@/lib/types";

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (payload: { email: string; password: string }) => Promise<void>;
  register: (payload: {
    email: string;
    password: string;
    full_name: string;
    tenant_name: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const restoreSession = async () => {
      const storedToken = getStoredToken();
      const storedUser = getStoredUser();

      if (storedToken && storedUser) {
        setToken(storedToken);
        setUser(storedUser);
        setIsLoading(false);
        return;
      }

      // Seamless Auto-Sign-In for Personal/Local Deployment
      try {
        const authData = await authApi.login({
          email: "vaibhav251001@gmail.com",
          password: "TradeDNA@2026",
        });
        setStoredAuth(authData.access_token, authData.user);
        setToken(authData.access_token);
        setUser(authData.user);
      } catch {
        try {
          const authData = await authApi.refresh();
          setStoredAuth(authData.access_token, authData.user);
          setToken(authData.access_token);
          setUser(authData.user);
        } catch {
          clearStoredAuth();
          setToken(null);
          setUser(null);
        }
      } finally {
        setIsLoading(false);
      }
    };

    restoreSession();
  }, []);

  const login = async (payload: { email: string; password: string }) => {
    const res = await authApi.login(payload);
    setUser(res.user);
    setToken(res.access_token);
    router.push("/dashboard/overview");
  };

  const register = async (payload: {
    email: string;
    password: string;
    full_name: string;
    tenant_name: string;
  }) => {
    const res = await authApi.register(payload);
    setUser(res.user);
    setToken(res.access_token);
    router.push("/dashboard/overview");
  };

  const logout = async () => {
    await authApi.logout();
    setUser(null);
    setToken(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token && !!user,
        isLoading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
