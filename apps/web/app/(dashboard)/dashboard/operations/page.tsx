import { Metadata } from "next";
import { OperationsDashboard } from "@/components/operations/OperationsDashboard";

export const metadata: Metadata = {
  title: "Operations & Telemetry | TradeDNA",
  description: "Real-time production observability, MT5 connector heartbeats, synchronization pipeline telemetry, and operational alarms.",
};

export default function OperationsPage() {
  return (
    <div className="py-6">
      <OperationsDashboard />
    </div>
  );
}
