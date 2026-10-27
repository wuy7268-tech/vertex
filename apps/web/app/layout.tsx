import type { Metadata } from "next";
import { Instrument_Serif, Outfit } from "next/font/google";
import { Suspense, type ReactNode } from "react";

import { Shell } from "@/components/shell";
import "./globals.css";

const sans = Outfit({ subsets: ["latin"], variable: "--font-outfit" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", variable: "--font-serif" });

export const metadata: Metadata = {
  title: "Vertex",
  description: "An agentic workspace for tasks, calendar, mail, documents, and GitHub.",
};

export const dynamic = "force-dynamic";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${serif.variable} font-sans antialiased`}>
        <Suspense fallback={<main className="p-10 text-sm text-muted">Loading workspace…</main>}>
          <Shell>{children}</Shell>
        </Suspense>
      </body>
    </html>
  );
}
