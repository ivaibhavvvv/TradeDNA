import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/providers/query-provider";
import { AuthProvider } from "@/components/providers/auth-provider";

export const metadata: Metadata = {
  title: "TradeDNA — Decode Your Trading | Exness Intelligence",
  description:
    "Enterprise-grade, Exness-exclusive trading intelligence platform providing deterministic financial reconciliation, quantitative analytics, and behavioral DNA decoding.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#070a11] text-slate-100 antialiased selection:bg-cyan-500 selection:text-black">
        <QueryProvider>
          <AuthProvider>{children}</AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
