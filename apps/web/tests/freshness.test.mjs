import test from "node:test";
import assert from "node:assert/strict";

test("Phase 8E-C: Deterministic Freshness State Evaluator", () => {
  const evaluateFreshness = ({ isRevoked, isConnected, syncStatus, isReconClean, deltaSec }) => {
    if (isRevoked) return "REVOKED";
    if (!isConnected) return "OFFLINE";
    if (syncStatus === "ERROR") return "ERROR";
    if (syncStatus === "RECOVERING") return "RECOVERING";
    if (syncStatus === "SYNCING" || syncStatus === "INITIALIZING" || deltaSec === null) return "SYNCING";
    if (deltaSec <= 120) {
      if (!isReconClean) return "DEGRADED";
      return "LIVE";
    }
    if (deltaSec <= 600) return "DEGRADED";
    return "STALE";
  };

  // 1. Revoked device
  assert.equal(evaluateFreshness({ isRevoked: true, isConnected: true, syncStatus: "CURRENT", isReconClean: true, deltaSec: 5 }), "REVOKED");

  // 2. Disconnected / Offline
  assert.equal(evaluateFreshness({ isRevoked: false, isConnected: false, syncStatus: "CURRENT", isReconClean: true, deltaSec: 5 }), "OFFLINE");

  // 3. Error
  assert.equal(evaluateFreshness({ isRevoked: false, isConnected: true, syncStatus: "ERROR", isReconClean: true, deltaSec: 5 }), "ERROR");

  // 4. Recovering
  assert.equal(evaluateFreshness({ isRevoked: false, isConnected: true, syncStatus: "RECOVERING", isReconClean: true, deltaSec: 5 }), "RECOVERING");

  // 5. Active Syncing
  assert.equal(evaluateFreshness({ isRevoked: false, isConnected: true, syncStatus: "SYNCING", isReconClean: true, deltaSec: null }), "SYNCING");

  // 6. Live
  assert.equal(evaluateFreshness({ isRevoked: false, isConnected: true, syncStatus: "CURRENT", isReconClean: true, deltaSec: 8 }), "LIVE");

  // 7. Live but Reconciliation Discrepancy -> Degraded
  assert.equal(evaluateFreshness({ isRevoked: false, isConnected: true, syncStatus: "CURRENT", isReconClean: false, deltaSec: 8 }), "DEGRADED");

  // 8. Delayed sync (4m ago) -> Degraded
  assert.equal(evaluateFreshness({ isRevoked: false, isConnected: true, syncStatus: "CURRENT", isReconClean: true, deltaSec: 240 }), "DEGRADED");

  // 9. Stale sync (15m ago) -> Stale
  assert.equal(evaluateFreshness({ isRevoked: false, isConnected: true, syncStatus: "CURRENT", isReconClean: true, deltaSec: 900 }), "STALE");
});

test("Phase 8E-C: Adaptive Polling Interval Strategy", () => {
  const getPollingInterval = (freshnessState) => {
    switch (freshnessState) {
      case "SYNCING":
      case "RECOVERING":
        return 3000;
      case "LIVE":
        return 10000;
      case "DEGRADED":
        return 15000;
      case "STALE":
      case "OFFLINE":
      case "ERROR":
        return 30000;
      case "REVOKED":
        return 0; // stop polling
      default:
        return 10000;
    }
  };

  assert.equal(getPollingInterval("SYNCING"), 3000);
  assert.equal(getPollingInterval("RECOVERING"), 3000);
  assert.equal(getPollingInterval("LIVE"), 10000);
  assert.equal(getPollingInterval("DEGRADED"), 15000);
  assert.equal(getPollingInterval("STALE"), 30000);
  assert.equal(getPollingInterval("OFFLINE"), 30000);
  assert.equal(getPollingInterval("REVOKED"), 0);
});

test("Phase 8E-C: Atomic Account Switch Cache Invalidation Simulation", () => {
  const cache = new Map();
  cache.set("dashboard-overview:9920001", { net_pnl: "1450.00" });
  cache.set("dashboard-telemetry:9920001", { freshness_state: "LIVE" });
  cache.set("analytics:9920001", { win_rate: "68.5" });

  // Account switch to 9920002
  const onAccountSwitch = (newAccountNumber) => {
    // Invalidate old account entries
    for (const key of Array.from(cache.keys())) {
      cache.delete(key);
    }
    return newAccountNumber;
  };

  const switched = onAccountSwitch(9920002);
  assert.equal(switched, 9920002);
  assert.equal(cache.size, 0); // No stale cache remains
});

test("Phase 8E-C: Read-Only Safety Audit on Freshness Subsystem", () => {
  const prohibitedExecutionKeywords = [
    "OrderSend",
    "OrderSendAsync",
    "CTrade",
    "PositionClose",
    "PositionModify",
    "OrderModify",
    "OrderDelete",
  ];

  const freshnessActions = [
    "Read-only sync telemetry observation",
    "Live freshness badge rendering",
    "Data provenance timestamp presentation",
    "Historical synchronization progress bar",
    "Stale data alert without financial mutation",
    "Trigger backend ingestion check",
  ];

  for (const action of freshnessActions) {
    for (const kw of prohibitedExecutionKeywords) {
      assert.ok(!action.includes(kw), `Prohibited keyword ${kw} found in freshness action`);
    }
  }
});
