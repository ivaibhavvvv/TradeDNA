"use client";

/**
 * TradeDNA Phase 8 - Dashboard Overview React Query Hook.
 * Consumes the Phase 8A Dashboard BFF endpoint with 15s polling and account context invalidation.
 */

import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { useAccountContext } from "@/components/providers/account-provider";
import { useAuth } from "@/components/providers/auth-provider";

export function useDashboardOverview() {
  const { isAuthenticated } = useAuth();
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  return useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_OVERVIEW(actNum),
    queryFn: () => dashboardApi.getOverview(actNum),
    enabled: isAuthenticated,
  });
}
