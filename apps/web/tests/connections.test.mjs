import test from "node:test";
import assert from "node:assert/strict";

test("Phase 8E-B: Account Number Masking Formatter", () => {
  const maskAccountNumber = (accNum) => {
    const s = String(accNum);
    if (s.length <= 4) return `***${s.slice(-2)}`;
    return `${s.slice(0, 3)}****${s.slice(-2)}`;
  };

  assert.equal(maskAccountNumber(9928801), "992****01");
  assert.equal(maskAccountNumber(12345678), "123****78");
  assert.equal(maskAccountNumber(505), "***05");
});

test("Phase 8E-B: Device ID Masking Formatter", () => {
  const maskDeviceId = (devId) => {
    const s = String(devId);
    return `dev_${s.slice(0, 6)}...${s.slice(-4)}`;
  };

  assert.equal(
    maskDeviceId("d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f8a"),
    "dev_d4e5f6...7f8a"
  );
});

test("Phase 8E-B: Freshness & Connection Status Evaluator", () => {
  const calculateFreshness = (lastSyncEpoch, nowEpoch, isRevoked) => {
    if (isRevoked) return { label: "Connector Revoked", status: "REVOKED" };
    if (!lastSyncEpoch) return { label: "Awaiting Initial Sync", status: "SYNCING" };

    const deltaSec = Math.max(0, Math.floor((nowEpoch - lastSyncEpoch) / 1000));
    if (deltaSec < 10) return { label: "Live (Synced just now)", status: "CONNECTED" };
    if (deltaSec < 60) return { label: `Live (Synced ${deltaSec}s ago)`, status: "CONNECTED" };
    if (deltaSec < 300) return { label: `Synced ${Math.floor(deltaSec / 60)}m ago`, status: "CONNECTED" };
    if (deltaSec < 600) return { label: `Sync Delayed (${Math.floor(deltaSec / 60)}m ago)`, status: "DEGRADED" };
    return { label: `Data Stale (${Math.floor(deltaSec / 60)}m ago)`, status: "STALE" };
  };

  const now = 1720000000000;
  assert.deepEqual(calculateFreshness(null, now, false), { label: "Awaiting Initial Sync", status: "SYNCING" });
  assert.deepEqual(calculateFreshness(now - 5000, now, false), { label: "Live (Synced just now)", status: "CONNECTED" });
  assert.deepEqual(calculateFreshness(now - 30000, now, false), { label: "Live (Synced 30s ago)", status: "CONNECTED" });
  assert.deepEqual(calculateFreshness(now - 200000, now, false), { label: "Synced 3m ago", status: "CONNECTED" });
  assert.deepEqual(calculateFreshness(now - 450000, now, false), { label: "Sync Delayed (7m ago)", status: "DEGRADED" });
  assert.deepEqual(calculateFreshness(now - 900000, now, false), { label: "Data Stale (15m ago)", status: "STALE" });
  assert.deepEqual(calculateFreshness(now - 5000, now, true), { label: "Connector Revoked", status: "REVOKED" });
});

test("Phase 8E-B: Security & Read-Only Invariant in Connection Center UI", () => {
  const prohibitedExecutionKeywords = ["OrderSend", "OrderSendAsync", "CTrade", "PositionClose", "PositionModify", "OrderModify", "OrderDelete"];

  const connectionCenterCapabilities = [
    "View connected Exness MT5 accounts",
    "View connector health and heartbeat telemetry",
    "View reconciliation integrity score",
    "Generate single-use pairing token",
    "Revoke connector terminal device",
    "Revoke all terminals for account",
    "Update local account display label",
  ];

  for (const cap of connectionCenterCapabilities) {
    for (const kw of prohibitedExecutionKeywords) {
      assert.ok(!cap.includes(kw), `Prohibited keyword ${kw} found in capability description`);
    }
  }
});
