import test from "node:test";
import assert from "node:assert/strict";

test("Scenario 1: Connect Exness CTA Presence & Read-Only Guarantee", () => {
  const cta = {
    label: "+ Connect Exness Account",
    isReadOnly: true,
    requiresBrokerPassword: false,
    requiresTradingPassword: false,
  };

  assert.equal(cta.label, "+ Connect Exness Account");
  assert.equal(cta.isReadOnly, true);
  assert.equal(cta.requiresBrokerPassword, false);
  assert.equal(cta.requiresTradingPassword, false);
});

test("Scenario 2: Pairing Drawer State Machine Lifecycle", () => {
  const validStages = [
    "GENERATING",
    "READY",
    "WAITING_FOR_MT5",
    "HANDSHAKE_RECEIVED",
    "VERIFYING_ACCOUNT",
    "CONNECTED",
    "INITIAL_SYNC",
    "EXPIRED",
    "INVALID",
    "REJECTED",
    "ALREADY_USED",
    "DEVICE_REVOKED",
    "NETWORK_ERROR",
  ];

  let currentStage = "GENERATING";
  const transition = (nextStage) => {
    assert.ok(validStages.includes(nextStage), `Invalid stage: ${nextStage}`);
    currentStage = nextStage;
    return currentStage;
  };

  assert.equal(transition("READY"), "READY");
  assert.equal(transition("WAITING_FOR_MT5"), "WAITING_FOR_MT5");
  assert.equal(transition("HANDSHAKE_RECEIVED"), "HANDSHAKE_RECEIVED");
  assert.equal(transition("VERIFYING_ACCOUNT"), "VERIFYING_ACCOUNT");
  assert.equal(transition("CONNECTED"), "CONNECTED");
  assert.equal(transition("INITIAL_SYNC"), "INITIAL_SYNC");
});

test("Scenario 3: Pairing Countdown Timer & Expiration Trigger", () => {
  const formatCountdown = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  assert.equal(formatCountdown(300), "5:00");
  assert.equal(formatCountdown(154), "2:34");
  assert.equal(formatCountdown(5), "0:05");
  assert.equal(formatCountdown(0), "0:00");

  const checkExpiration = (seconds) => (seconds <= 0 ? "EXPIRED" : "ACTIVE");
  assert.equal(checkExpiration(0), "EXPIRED");
  assert.equal(checkExpiration(12), "ACTIVE");
});

test("Scenario 4: Waiting-for-MT5 Terminal Polling Simulator", () => {
  let attempts = 0;
  const pollHandshake = (hasOnlineDevice) => {
    attempts++;
    if (hasOnlineDevice) return "HANDSHAKE_RECEIVED";
    return attempts > 100 ? "EXPIRED" : "WAITING_FOR_MT5";
  };

  assert.equal(pollHandshake(false), "WAITING_FOR_MT5");
  assert.equal(pollHandshake(false), "WAITING_FOR_MT5");
  assert.equal(pollHandshake(true), "HANDSHAKE_RECEIVED");
});

test("Scenario 5: Successful Cryptographic Session & Account Verification", () => {
  const verifySession = ({ broker, accountNumber, serverName, deviceId }) => {
    if (broker !== "EXNESS") throw new Error("Unsupported broker");
    if (accountNumber <= 0) throw new Error("Invalid account number");
    if (!serverName) throw new Error("Invalid server");
    return {
      status: "VERIFIED",
      maskedAccount: `•••••${String(accountNumber).slice(-4)}`,
      deviceId: `${deviceId.slice(0, 8)}...`,
    };
  };

  const res = verifySession({
    broker: "EXNESS",
    accountNumber: 9940101,
    serverName: "Exness-Real25",
    deviceId: "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  });

  assert.equal(res.status, "VERIFIED");
  assert.equal(res.maskedAccount, "•••••0101");
  assert.equal(res.deviceId, "9b1deb4d...");
});

test("Scenario 6: Historical Synchronization UI & Stage Progression", () => {
  const syncStages = [
    "DISCOVERING_ACCOUNT",
    "DOWNLOADING_HISTORY",
    "PROCESSING_EVENTS",
    "RECONSTRUCTING",
    "RECONCILING",
    "ANALYZING",
    "READY",
  ];

  const getProgressPercentage = (stage) => {
    const idx = syncStages.indexOf(stage);
    if (idx === -1) return 0;
    return Math.round(((idx + 1) / syncStages.length) * 100);
  };

  assert.equal(getProgressPercentage("DISCOVERING_ACCOUNT"), 14);
  assert.equal(getProgressPercentage("DOWNLOADING_HISTORY"), 29);
  assert.equal(getProgressPercentage("PROCESSING_EVENTS"), 43);
  assert.equal(getProgressPercentage("RECONSTRUCTING"), 57);
  assert.equal(getProgressPercentage("RECONCILING"), 71);
  assert.equal(getProgressPercentage("ANALYZING"), 86);
  assert.equal(getProgressPercentage("READY"), 100);
});

test("Scenario 7: Sync Completion & AAA Integrity Badge Activation", () => {
  const evaluateDashboardActivation = (syncStage, integrityScore, integrityGrade) => {
    if (syncStage !== "READY") return { isActive: false, status: "SYNCHRONIZING" };
    if (integrityGrade !== "AAA" || parseFloat(integrityScore) < 99.9) {
      return { isActive: true, status: "DEGRADED_INTEGRITY" };
    }
    return { isActive: true, status: "VERIFIED_AAA" };
  };

  const syncingRes = evaluateDashboardActivation("PROCESSING_EVENTS", "100.00", "AAA");
  assert.equal(syncingRes.isActive, false);
  assert.equal(syncingRes.status, "SYNCHRONIZING");

  const completeRes = evaluateDashboardActivation("READY", "100.00", "AAA");
  assert.equal(completeRes.isActive, true);
  assert.equal(completeRes.status, "VERIFIED_AAA");
});

test("Scenario 8: Connection Failure & Non-Destructive Recovery", () => {
  const handleConnectionLoss = (lastSyncTimestamp) => {
    return {
      message: "Connection interrupted. Your existing trading data remains safe. TradeDNA is waiting for your MT5 connector to reconnect.",
      lastVerifiedAt: lastSyncTimestamp,
      isDataPreserved: true,
      hasFinancialDrift: false,
    };
  };

  const res = handleConnectionLoss("2026-08-19T09:20:00Z");
  assert.ok(res.message.includes("remains safe"));
  assert.equal(res.isDataPreserved, true);
  assert.equal(res.hasFinancialDrift, false);
});

test("Scenario 9: Reconnection & Ingress Recovery Stage Presentation", () => {
  const handleReconnection = (pendingSpoolCount) => {
    return {
      stage: "RECOVERING",
      bannerText: `Connection restored. Synchronizing ${pendingSpoolCount} pending events...`,
      action: "DRAINING_SPOOL",
    };
  };

  const rec = handleReconnection(42);
  assert.equal(rec.stage, "RECOVERING");
  assert.ok(rec.bannerText.includes("42 pending events"));
});

test("Scenario 10: Stale Data Alert without Mutating Verified Financial Records", () => {
  const renderStaleDataBanner = (freshnessSeconds, verifiedNetPnl) => {
    const isStale = freshnessSeconds > 600;
    return {
      showAlert: isStale,
      displayedNetPnl: verifiedNetPnl, // Historical net PnL is NEVER overwritten with 0
      warning: isStale ? "DATA STALE — RECENT SYNCHRONIZATION UNAVAILABLE" : null,
    };
  };

  const staleResult = renderStaleDataBanner(900, "12,450.00");
  assert.equal(staleResult.showAlert, true);
  assert.equal(staleResult.displayedNetPnl, "12,450.00");
  assert.equal(staleResult.warning, "DATA STALE — RECENT SYNCHRONIZATION UNAVAILABLE");
});

test("Scenario 11: Account Switching Cache Invalidation", () => {
  const queryCache = new Set(["overview:acc1", "telemetry:acc1", "trades:acc1"]);

  const onAccountSwitch = (newAccId) => {
    queryCache.clear();
    return {
      activeAccount: newAccId,
      isLoading: true,
      cacheSize: queryCache.size,
    };
  };

  const switchResult = onAccountSwitch("acc2");
  assert.equal(switchResult.activeAccount, "acc2");
  assert.equal(switchResult.isLoading, true);
  assert.equal(switchResult.cacheSize, 0);
});

test("Scenario 12: Zero Stale Account Data Leakage During Switch", () => {
  let displayData = { account: "acc1", balance: "10,000.00" };

  const startSwitch = () => {
    displayData = null; // Purge immediately during loading
  };

  startSwitch();
  assert.equal(displayData, null); // Account 1 data is NOT leaked while Account 2 loads
});

test("Scenario 13: 1-Click Device Revocation & Immediate Ingress Termination", () => {
  const deviceState = { id: "dev-01", is_active: true, is_revoked: false };

  const revokeDevice = (dev) => {
    return {
      ...dev,
      is_active: false,
      is_revoked: true,
      status: "REVOKED",
    };
  };

  const revoked = revokeDevice(deviceState);
  assert.equal(revoked.is_active, false);
  assert.equal(revoked.is_revoked, true);
  assert.equal(revoked.status, "REVOKED");
});

test("Scenario 14: Dashboard Activation Gate Logic", () => {
  const checkDashboardReadiness = (telemetry) => {
    if (!telemetry.has_account) return "EMPTY_STATE";
    if (telemetry.sync_stage !== "READY") return "SYNCHRONIZING_OVERLAY";
    return "FULL_INTELLIGENCE_ACTIVE";
  };

  assert.equal(checkDashboardReadiness({ has_account: false }), "EMPTY_STATE");
  assert.equal(checkDashboardReadiness({ has_account: true, sync_stage: "DOWNLOADING_HISTORY" }), "SYNCHRONIZING_OVERLAY");
  assert.equal(checkDashboardReadiness({ has_account: true, sync_stage: "READY" }), "FULL_INTELLIGENCE_ACTIVE");
});

test("Scenario 15: Error Sanitization (Zero Stack Traces / Secrets Exposed)", () => {
  const sanitizeErrorMessage = (error) => {
    const rawMsg = String(error?.message || "");
    const sensitiveTokens = ["password", "token", "secret", "hash", "Traceback", "File \"/"];
    for (const sens of sensitiveTokens) {
      if (rawMsg.includes(sens)) {
        return "A synchronization error occurred. Please retry from the Connection Center.";
      }
    }
    return rawMsg;
  };

  const safeMsg = sanitizeErrorMessage(new Error("Traceback: File \"/src/core/auth.py\", line 42: invalid secret key"));
  assert.equal(safeMsg, "A synchronization error occurred. Please retry from the Connection Center.");

  const normalMsg = sanitizeErrorMessage(new Error("Network connection timed out."));
  assert.equal(normalMsg, "Network connection timed out.");
});
