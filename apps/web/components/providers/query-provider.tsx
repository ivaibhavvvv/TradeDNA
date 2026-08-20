"use client";

/**
 * TradeDNA Phase 8 - TanStack React Query Provider.
 * Implements standard polling intervals (15s), pauses in background, and invalidation rules.
 */

import React, { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { POLLING_CONFIG } from "@/lib/constants";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchInterval: POLLING_CONFIG.REFETCH_INTERVAL_MS,
            refetchIntervalInBackground: POLLING_CONFIG.REFETCH_IN_BACKGROUND,
            refetchOnWindowFocus: POLLING_CONFIG.REFETCH_ON_WINDOW_FOCUS,
            staleTime: POLLING_CONFIG.STALE_TIME_MS,
            retry: 1,
          },
        },
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
