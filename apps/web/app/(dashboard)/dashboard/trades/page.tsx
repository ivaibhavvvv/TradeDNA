"use client";

/**
 * TradeDNA Phase 8C - Canonical Trades Ledger & Execution Lineage Page.
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Filter,
  ReceiptText,
  Search,
  ShieldAlert,
  SlidersHorizontal,
} from "lucide-react";
import { useAccountContext } from "@/components/providers/account-provider";
import { dashboardApi } from "@/lib/api-client";
import { QUERY_KEYS } from "@/lib/constants";
import { CanonicalTradeItem, TradeDetailResponse } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency } from "@/lib/utils";

export default function TradesPage() {
  const { selectedAccount } = useAccountContext();
  const actNum = selectedAccount?.account_number;

  // Filter & Pagination state
  const [page, setPage] = useState(0);
  const pageSize = 20;
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState("");
  const [result, setResult] = useState("");
  const [sortBy, setSortBy] = useState("opened_at_utc");
  const [sortOrder, setSortOrder] = useState("desc");

  // Selected trade for detail modal
  const [selectedTradeId, setSelectedTradeId] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_TRADES(actNum, {
      offset: page * pageSize,
      limit: pageSize,
      search,
      direction,
      result,
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    queryFn: () =>
      dashboardApi.getTrades(actNum, {
        offset: page * pageSize,
        limit: pageSize,
        search: search || undefined,
        direction: direction || undefined,
        result: result || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      }),
    enabled: !!actNum,
  });

  // Query trade detail on demand
  const { data: tradeDetail, isLoading: isLoadingDetail } = useQuery({
    queryKey: QUERY_KEYS.DASHBOARD_TRADE_DETAIL(selectedTradeId || ""),
    queryFn: () => dashboardApi.getTradeDetail(selectedTradeId!),
    enabled: !!selectedTradeId,
  });

  const totalPages = Math.ceil((data?.total_count || 0) / pageSize);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
            CANONICAL TRADES & EXECUTION AUDIT
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic trade reconstructions, FIFO lot allocation, and deal lineage.
          </p>
        </div>
        <Badge variant="neutral">Strictly Read-Only</Badge>
      </div>

      {/* Filter Controls Bar */}
      <Card className="border-slate-800 bg-[#0d1321]">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
            {/* Search */}
            <div className="relative md:col-span-2">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <Input
                placeholder="Search symbol (e.g. XAUUSD)..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
                className="pl-9 text-xs"
              />
            </div>

            {/* Direction Filter */}
            <Select
              value={direction}
              onChange={(e) => {
                setDirection(e.target.value);
                setPage(0);
              }}
              className="text-xs"
            >
              <option value="">All Directions</option>
              <option value="BUY">BUY (Long)</option>
              <option value="SELL">SELL (Short)</option>
            </Select>

            {/* Result Filter */}
            <Select
              value={result}
              onChange={(e) => {
                setResult(e.target.value);
                setPage(0);
              }}
              className="text-xs"
            >
              <option value="">All Outcomes</option>
              <option value="WIN">Winning Trades</option>
              <option value="LOSS">Losing Trades</option>
            </Select>

            {/* Sort Filter */}
            <Select
              value={`${sortBy}_${sortOrder}`}
              onChange={(e) => {
                const [sb, so] = e.target.value.split("_");
                setSortBy(sb);
                setSortOrder(so);
                setPage(0);
              }}
              className="text-xs"
            >
              <option value="opened_at_utc_desc">Newest First</option>
              <option value="opened_at_utc_asc">Oldest First</option>
              <option value="realized_net_pnl_desc">Highest Profit</option>
              <option value="realized_net_pnl_asc">Highest Loss</option>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Trades Table */}
      <Card className="border-slate-800 bg-[#0d1321] overflow-hidden">
        <CardHeader className="pb-3 border-b border-slate-800 flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-slate-200">
              Canonical Trade Ledger
            </CardTitle>
            <CardDescription className="text-xs text-slate-400">
              Total {data?.total_count || 0} matching reconstructed trades
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : isError ? (
            <div className="p-6">
              <ErrorState
                title="Failed to Load Trades"
                message={error?.message || "Could not retrieve canonical trades ledger."}
                onRetry={() => refetch()}
              />
            </div>
          ) : data?.items?.length === 0 ? (
            <div className="p-12 text-center text-xs font-mono text-slate-500">
              No canonical trades match the applied filters.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-slate-800/80 bg-slate-900/60">
                  <TableHead>Ticket / Symbol</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Volume</TableHead>
                  <TableHead>Entry Price</TableHead>
                  <TableHead>Exit Price</TableHead>
                  <TableHead>Open Time (UTC)</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead className="text-right">Commission / Swap</TableHead>
                  <TableHead className="text-right">Realized Net P&L</TableHead>
                  <TableHead className="text-center">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items.map((trade) => {
                  const pnl = parseFloat(trade.realized_net_pnl);
                  const isProfit = pnl >= 0;
                  const durationMin = trade.duration_seconds
                    ? Math.floor(trade.duration_seconds / 60)
                    : 0;

                  return (
                    <TableRow
                      key={trade.id}
                      className="cursor-pointer hover:bg-slate-800/60 transition-colors"
                      onClick={() => setSelectedTradeId(trade.id)}
                    >
                      <TableCell>
                        <div className="font-mono font-bold text-slate-200">{trade.symbol}</div>
                        <div className="text-[10px] text-slate-500 font-mono">#{trade.position_ticket}</div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={trade.side === "BUY" ? "positive" : "negative"}
                          className="font-mono text-[10px]"
                        >
                          {trade.side}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-slate-200">
                        {trade.total_entry_volume} lots
                      </TableCell>
                      <TableCell className="font-mono text-xs text-slate-300">
                        {trade.vwap_entry_price}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-slate-300">
                        {trade.vwap_exit_price || "—"}
                      </TableCell>
                      <TableCell className="font-mono text-[11px] text-slate-400">
                        {new Date(trade.opened_at_utc).toLocaleString([], {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </TableCell>
                      <TableCell className="font-mono text-[11px] text-slate-400">
                        {durationMin > 0 ? `${durationMin}m` : "<1m"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-[11px] text-slate-400">
                        {formatCurrency(parseFloat(trade.total_commission) + parseFloat(trade.total_swap), data.currency)}
                      </TableCell>
                      <TableCell className="text-right">
                        <span
                          className={`font-mono font-bold text-xs ${
                            isProfit ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {formatCurrency(trade.realized_net_pnl, data.currency)}
                        </span>
                      </TableCell>
                      <TableCell className="text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[11px] text-cyan-400 hover:text-cyan-300 h-7 px-2"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedTradeId(trade.id);
                          }}
                        >
                          Lineage
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800 text-xs">
              <span className="text-slate-400 font-mono">
                Page {page + 1} of {totalPages} ({data?.total_count} total trades)
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  className="h-8 gap-1 text-xs"
                >
                  <ChevronLeft className="h-3.5 w-3.5" /> Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                  className="h-8 gap-1 text-xs"
                >
                  Next <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Trade Detail & Execution Lineage Modal */}
      <Dialog
        open={!!selectedTradeId}
        onOpenChange={(open) => {
          if (!open) setSelectedTradeId(null);
        }}
        title={`Canonical Trade Lineage: #${tradeDetail?.position_ticket || ""}`}
        description="Deterministic lot matching, fee breakdown, and behavioral citations."
      >
        {isLoadingDetail || !tradeDetail ? (
          <div className="space-y-3 p-4 animate-pulse">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
          </div>
        ) : (
          <div className="space-y-4 text-xs font-mono">
            <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-900/80 p-3 border border-slate-800">
              <div>
                <span className="text-[10px] text-slate-500 font-sans">Symbol & Side:</span>
                <div className="font-bold text-slate-100 mt-0.5">
                  {tradeDetail.symbol} • <span className={tradeDetail.side === "BUY" ? "text-emerald-400" : "text-rose-400"}>{tradeDetail.side}</span>
                </div>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 font-sans">Net Realized P&L:</span>
                <div className={`font-bold text-sm mt-0.5 ${parseFloat(tradeDetail.realized_net_pnl) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {formatCurrency(tradeDetail.realized_net_pnl, data?.currency || "USD")}
                </div>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 font-sans">VWAP Entry / Exit:</span>
                <div className="text-slate-200 mt-0.5">
                  {tradeDetail.vwap_entry_price} → {tradeDetail.vwap_exit_price || "Open"}
                </div>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 font-sans">Volume & Fees:</span>
                <div className="text-slate-200 mt-0.5">
                  {tradeDetail.total_entry_volume} lots • Fee: {formatCurrency(tradeDetail.total_fees, data?.currency || "USD")}
                </div>
              </div>
            </div>

            {/* Timestamps */}
            <div className="rounded-lg bg-slate-900/50 p-3 border border-slate-800/80 space-y-1.5 text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-400 font-sans">Opened At (UTC):</span>
                <span className="text-slate-200">{new Date(tradeDetail.opened_at_utc).toISOString()}</span>
              </div>
              {tradeDetail.closed_at_utc && (
                <div className="flex justify-between">
                  <span className="text-slate-400 font-sans">Closed At (UTC):</span>
                  <span className="text-slate-200">{new Date(tradeDetail.closed_at_utc).toISOString()}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-slate-400 font-sans">Holding Duration:</span>
                <span className="text-slate-200">{tradeDetail.duration_seconds ? `${tradeDetail.duration_seconds} seconds` : "N/A"}</span>
              </div>
            </div>

            {/* Behavioral Citations */}
            {tradeDetail.behavioral_citations && tradeDetail.behavioral_citations.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <span className="text-[10px] uppercase font-semibold text-amber-400 tracking-wider font-sans flex items-center gap-1.5">
                  <ShieldAlert className="h-3.5 w-3.5" />
                  Behavioral Anomalies Citing this Trade
                </span>
                {tradeDetail.behavioral_citations.map((c, i) => (
                  <div key={i} className="rounded-md border border-amber-900/50 bg-amber-950/20 p-2 text-[11px] flex justify-between items-center">
                    <span className="text-amber-200">{c.pattern_type.replace(/_/g, " ")}</span>
                    <Badge variant={c.severity === "CRITICAL" ? "critical" : "warning"}>{c.severity}</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Dialog>
    </div>
  );
}
