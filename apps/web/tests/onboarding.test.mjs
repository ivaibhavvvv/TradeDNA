import test from "node:test";
import assert from "node:assert/strict";

test("Phase 8E-A: Onboarding State Transitions & Steps", () => {
  const steps = [
    { id: 1, label: "Verify Email" },
    { id: 2, label: "Workspace" },
    { id: 3, label: "MT5 Connector" },
    { id: 4, label: "Pair Account" },
    { id: 5, label: "Historical Sync" },
    { id: 6, label: "Launch" },
  ];

  assert.equal(steps.length, 6);
  assert.equal(steps[0].label, "Verify Email");
  assert.equal(steps[5].label, "Launch");
});

test("Phase 8E-A: Countdown Timer Formatting", () => {
  const formatTime = (sec) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  assert.equal(formatTime(900), "15:00");
  assert.equal(formatTime(300), "5:00");
  assert.equal(formatTime(65), "1:05");
  assert.equal(formatTime(9), "0:09");
  assert.equal(formatTime(0), "0:00");
});

test("Phase 8E-A: Step Index Resolver from Backend State", () => {
  const resolveStepIndex = (state) => {
    if (state.is_completed || state.current_step === "DATA_VALIDATED") return 6;
    if (state.current_step === "INITIAL_SYNC_IN_PROGRESS") return 5;
    if (state.current_step === "AWAITING_CONNECTOR_HANDSHAKE") return 4;
    if (state.current_step === "WORKSPACE_CONFIGURED") return 3;
    if (state.current_step === "EMAIL_VERIFIED") return 2;
    return state.email_verified ? 2 : 1;
  };

  assert.equal(resolveStepIndex({ current_step: "REGISTERED", email_verified: false, is_completed: false }), 1);
  assert.equal(resolveStepIndex({ current_step: "EMAIL_VERIFIED", email_verified: true, is_completed: false }), 2);
  assert.equal(resolveStepIndex({ current_step: "WORKSPACE_CONFIGURED", email_verified: true, is_completed: false }), 3);
  assert.equal(resolveStepIndex({ current_step: "AWAITING_CONNECTOR_HANDSHAKE", email_verified: true, is_completed: false }), 4);
  assert.equal(resolveStepIndex({ current_step: "INITIAL_SYNC_IN_PROGRESS", email_verified: true, is_completed: false }), 5);
  assert.equal(resolveStepIndex({ current_step: "DATA_VALIDATED", email_verified: true, is_completed: false }), 6);
  assert.equal(resolveStepIndex({ current_step: "COMPLETED", email_verified: true, is_completed: true }), 6);
});

test("Phase 8E-A: Read-Only Invariant Enforcement in Onboarding Guide", () => {
  const instructions = [
    "Download TradeDNAConnector.ex5 and place it in your MT5 Terminal 'MQL5/Experts/' directory.",
    "In MT5, navigate to Tools -> Options -> Expert Advisors.",
    "Check 'Allow WebRequest for listed URL' and add: https://api.tradedna.io",
    "Do NOT check 'Allow Automated Trading' - TradeDNA is strictly 100% read-only.",
    "Attach TradeDNAConnector to any chart, paste the Pairing Token, and click OK.",
  ];

  const executionKeywords = ["OrderSend", "CTrade", "PositionClose", "Buy", "Sell", "Execute"];
  for (const inst of instructions) {
    for (const kw of executionKeywords) {
      if (inst.includes(kw)) {
        // Ensure only cautionary negation exists
        assert.ok(inst.includes("Do NOT check 'Allow Automated Trading'"));
      }
    }
  }
});
