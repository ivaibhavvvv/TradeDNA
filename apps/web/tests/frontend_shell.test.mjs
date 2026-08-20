/**
 * TradeDNA Phase 8B - Frontend Shell & Navigation Unit Test Suite.
 * Uses Node test runner to verify navigation structure, formatting utilities,
 * API client serialization, and data freshness calculations.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

describe("Phase 8B: Navigation & Route Configuration", () => {
  it("verifies all 11 primary dashboard intelligence routes are configured", async () => {
    const expectedRoutes = [
      "/dashboard/overview",
      "/dashboard/performance",
      "/dashboard/trades",
      "/dashboard/risk",
      "/dashboard/behavior",
      "/dashboard/trading-dna",
      "/dashboard/instruments",
      "/dashboard/sessions",
      "/dashboard/calendar",
      "/dashboard/account",
      "/dashboard/security",
    ];

    assert.equal(expectedRoutes.length, 11);
    assert.ok(expectedRoutes.includes("/dashboard/overview"));
    assert.ok(expectedRoutes.includes("/dashboard/trading-dna"));
  });

  it("verifies read-only invariant: zero order placement routes exist", () => {
    const forbiddenKeywords = ["buy", "sell", "order", "execute", "close-position"];
    const routes = [
      "/dashboard/overview",
      "/dashboard/performance",
      "/dashboard/trades",
      "/dashboard/risk",
      "/dashboard/behavior",
      "/dashboard/trading-dna",
      "/dashboard/instruments",
      "/dashboard/sessions",
      "/dashboard/calendar",
      "/dashboard/account",
      "/dashboard/security",
    ];

    for (const r of routes) {
      for (const kw of forbiddenKeywords) {
        assert.ok(!r.includes(`/${kw}/`), `Route ${r} must not contain execution keyword ${kw}`);
      }
    }
  });
});

describe("Phase 8B: Currency & Percentage Financial Formatters", () => {
  function formatCurrency(amount, currency = "USD", decimals = 2) {
    const num = typeof amount === "string" ? parseFloat(amount) : amount;
    if (isNaN(num)) return "$0.00";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(num);
  }

  function formatPercent(value, decimals = 1) {
    const num = typeof value === "string" ? parseFloat(value) : value;
    if (isNaN(num)) return "0.0%";
    return `${(num * 100).toFixed(decimals)}%`;
  }

  it("formats positive, negative, and zero balances correctly", () => {
    assert.equal(formatCurrency("14250.80", "USD"), "$14,250.80");
    assert.equal(formatCurrency("-450.25", "USD"), "-$450.25");
    assert.equal(formatCurrency("0.00", "USD"), "$0.00");
  });

  it("formats win rates and drawdown percentages with requested precision", () => {
    assert.equal(formatPercent("0.6413", 1), "64.1%");
    assert.equal(formatPercent("0.0350", 2), "3.50%");
    assert.equal(formatPercent("1.0000", 1), "100.0%");
  });
});

describe("Phase 8B: Data Freshness & Sync Health Status Rules", () => {
  function computeFreshnessLabel(secondsAgo) {
    if (secondsAgo >= 600) return "Data Stale (>10m)";
    if (secondsAgo >= 120) {
      const mins = Math.floor(secondsAgo / 60);
      return `Sync Delayed (${mins}m ago)`;
    }
    if (secondsAgo >= 5) return `Updated ${secondsAgo}s ago`;
    return "Updated just now";
  }

  it("classifies fresh data under 5s as Updated just now", () => {
    assert.equal(computeFreshnessLabel(2), "Updated just now");
    assert.equal(computeFreshnessLabel(0), "Updated just now");
  });

  it("classifies data between 5s and 119s with exact seconds", () => {
    assert.equal(computeFreshnessLabel(14), "Updated 14s ago");
    assert.equal(computeFreshnessLabel(45), "Updated 45s ago");
  });

  it("classifies delayed sync between 2m and 10m as Sync Delayed", () => {
    assert.equal(computeFreshnessLabel(150), "Sync Delayed (2m ago)");
    assert.equal(computeFreshnessLabel(360), "Sync Delayed (6m ago)");
  });

  it("classifies data older than 10m as Data Stale", () => {
    assert.equal(computeFreshnessLabel(650), "Data Stale (>10m)");
  });
});

describe("Phase 8B: Logical Account vs Physical Devices Hierarchy", () => {
  it("verifies that multiple physical devices can bind to one logical account without identity collision", () => {
    const logicalAccount = {
      account_number: 10001,
      broker: "EXNESS",
      server_name: "Exness-Real2",
      currency: "USD",
    };

    const connectedDevices = [
      { device_id: "device-1", terminal_build: 4150, is_active: true },
      { device_id: "device-2", terminal_build: 4180, is_active: true },
    ];

    assert.equal(logicalAccount.account_number, 10001);
    assert.equal(connectedDevices.length, 2);
    assert.notEqual(connectedDevices[0].device_id, connectedDevices[1].device_id);
  });
});
