import React, { createContext, useContext, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { AuthorizedAccount, SyncTelemetry } from "@/lib/types";
import { useAuth } from "./auth-provider";

interface AccountContextType {
  accounts: AuthorizedAccount[];
  selectedAccount: AuthorizedAccount | null;
  setSelectedAccount: (account: AuthorizedAccount) => void;
  telemetry: SyncTelemetry | null;
  isLoadingAccounts: boolean;
  isLoadingTelemetry: boolean;
  refetchAccounts: () => void;
  refetchTelemetry: () => void;
}

const AccountContext = createContext<AccountContextType | undefined>(undefined);

export function AccountProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const [selectedAccount, setSelectedAccountState] = useState<AuthorizedAccount | null>(null);

  // 1. Fetch Authorized Accounts
  const {
    data: accounts = [],
    isLoading: isLoadingAccounts,
    refetch: refetchAccounts,
  } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_ACCOUNTS,
    queryFn: () => dashboardApi.getAccounts(),
    enabled: isAuthenticated,
  });

  useEffect(() => {
    if (accounts.length > 0) {
      if (!selectedAccount || !accounts.some((a) => a.account_number === selectedAccount.account_number)) {
        setSelectedAccountState(accounts[0]);
      }
    } else {
      setSelectedAccountState(null);
    }
  }, [accounts, selectedAccount]);

  // 2. Fetch Authoritative Sync Telemetry with Adaptive Polling
  const {
    data: telemetry = null,
    isLoading: isLoadingTelemetry,
    refetch: refetchTelemetry,
  } = useQuery({
    queryKey: ["dashboard-telemetry", selectedAccount?.account_number],
    queryFn: () => dashboardApi.getSyncTelemetry(selectedAccount?.account_number),
    enabled: isAuthenticated && !!selectedAccount,
    refetchInterval: (query) => {
      const data = query.state.data as SyncTelemetry | undefined;
      if (!data) return 5000;
      if (data.freshness_state === "REVOKED") return false;
      return data.suggested_polling_interval_ms || 10000;
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });

  // 3. Atomic Account Switching with Zero Stale Leakage
  const setSelectedAccount = (account: AuthorizedAccount) => {
    if (selectedAccount?.account_number === account.account_number) return;

    // Immediately cancel pending queries and invalidate all module caches
    queryClient.cancelQueries();
    queryClient.removeQueries({ queryKey: ["dashboard-overview"] });
    queryClient.removeQueries({ queryKey: ["dashboard-telemetry"] });
    queryClient.removeQueries({ queryKey: ["analytics"] });

    setSelectedAccountState(account);
  };

  return (
    <AccountContext.Provider
      value={{
        accounts,
        selectedAccount,
        setSelectedAccount,
        telemetry: telemetry || null,
        isLoadingAccounts,
        isLoadingTelemetry,
        refetchAccounts,
        refetchTelemetry,
      }}
    >
      {children}
    </AccountContext.Provider>
  );
}

export function useAccountContext() {
  const context = useContext(AccountContext);
  if (!context) {
    throw new Error("useAccountContext must be used within an AccountProvider");
  }
  return context;
}

