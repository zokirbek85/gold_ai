import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Gold AI — Trading Intelligence Platform",
  description: "Professional XAUUSD analysis: Technical, SMC, ML, AI, News",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#0a0a0f] text-gray-100 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
