"use client";

/**
 * TradeDNA Phase 8 - Sync Trigger Mutation Hook.
 * Triggers backend synchronization and invalidates overview queries.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api-client";
import { useAccountContext } from "@/components/providers/account-provider";

export function useSyncTrigger() {
  const queryClient = useQueryClient();
  const { selectedAccount, refetchAccounts } = useAccountContext();

  return useMutation({
    mutationFn: async () => {
      if (!selectedAccount) throw new Error("No Exness account selected");
      return dashboardApi.triggerSync(selectedAccount.account_number);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
      refetchAccounts();
    },
  });
}
