import { Metadata } from "next";
import { RecoveryDashboard } from "@/components/recovery/RecoveryDashboard";

export const metadata: Metadata = {
  title: "Disaster Recovery & Backups | TradeDNA",
  description: "Automated database backups, deterministic financial checksums, point-in-time recovery verification, and RPO/RTO metrics.",
};

export default function RecoveryPage() {
  return (
    <div className="py-6">
      <RecoveryDashboard />
    </div>
  );
}
