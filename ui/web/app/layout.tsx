import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Agent Workbench",
  description: "Enterprise AI Agent Workbench — demo console",
};

// The CSP nonce is minted per request in middleware.ts, and Next can only stamp
// it onto the scripts it emits while it is actually rendering. A page served
// from the full route cache was prerendered at build time, before any nonce
// existed, so its scripts carry none and the browser refuses every one of them.
// Opting the whole console out of that cache is what makes the nonce work — and
// it is the right default regardless: every page here reads live data from the
// gateway, so there was nothing worth caching for a year.
export const dynamic = "force-dynamic";

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-950 text-zinc-100 antialiased">
        {children}
      </body>
    </html>
  );
}
