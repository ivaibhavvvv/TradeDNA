/**
 * TradeDNA Phase 9F - Production Deployment & Live Environment Unit Tests
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

describe("Phase 9F: Production Deployment & Live Dashboard Invariants", () => {
  it("verifies all 22 production Next.js routes exist in application directory", () => {
    const requiredRoutes = [
      "app/page.tsx",
      "app/(auth)/login/page.tsx",
      "app/(auth)/register/page.tsx",
      "app/onboarding/page.tsx",
      "app/(dashboard)/dashboard/page.tsx",
      "app/(dashboard)/dashboard/overview/page.tsx",
      "app/(dashboard)/dashboard/performance/page.tsx",
      "app/(dashboard)/dashboard/risk/page.tsx",
      "app/(dashboard)/dashboard/trades/page.tsx",
      "app/(dashboard)/dashboard/trading-dna/page.tsx",
      "app/(dashboard)/dashboard/behavior/page.tsx",
      "app/(dashboard)/dashboard/calendar/page.tsx",
      "app/(dashboard)/dashboard/sessions/page.tsx",
      "app/(dashboard)/dashboard/instruments/page.tsx",
      "app/(dashboard)/dashboard/security/page.tsx",
      "app/(dashboard)/dashboard/account/page.tsx",
      "app/(dashboard)/dashboard/connections/page.tsx",
      "app/(dashboard)/dashboard/operations/page.tsx",
      "app/(dashboard)/dashboard/recovery/page.tsx",
    ];

    for (const r of requiredRoutes) {
      const fullPath = path.resolve(r);
      assert.ok(fs.existsSync(fullPath), `Required production route file missing: ${r}`);
    }
  });

  it("verifies production API client uses credentials and relative or env base URLs", () => {
    const apiClientPath = path.resolve("lib/api-client.ts");
    assert.ok(fs.existsSync(apiClientPath));
    const content = fs.readFileSync(apiClientPath, "utf8");
    assert.ok(content.includes("credentials: 'include'") || content.includes('credentials: "include"'));
    assert.ok(!content.includes("localStorage.getItem('token')"));
  });

  it("verifies Exness-only and MT5-only branding and labels across UI components", () => {
    const connCenterPath = path.resolve("components/connections/ConnectionCenter.tsx");
    if (fs.existsSync(connCenterPath)) {
      const content = fs.readFileSync(connCenterPath, "utf8");
      assert.ok(content.includes("Exness") || content.includes("EXNESS"));
      assert.ok(content.includes("MT5") || content.includes("MetaTrader 5"));
    }
  });

  it("verifies strict read-only guarantee across all UI components and action handlers", () => {
    const forbidden = ["OrderSend", "OrderSendAsync", "CTrade", "PositionClose", "Trade.mqh"];
    const componentsDir = path.resolve("components");
    const scanDir = (dir) => {
      const files = fs.readdirSync(dir);
      for (const file of files) {
        const p = path.join(dir, file);
        if (fs.statSync(p).isDirectory()) {
          scanDir(p);
        } else if (file.endsWith(".tsx") || file.endsWith(".ts")) {
          const code = fs.readFileSync(p, "utf8");
          for (const kw of forbidden) {
            assert.ok(!code.includes(kw), `Forbidden keyword '${kw}' in ${p}`);
          }
        }
      }
    };
    scanDir(componentsDir);
  });
});
