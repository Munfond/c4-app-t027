import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "P-027 Perception Lab",
  description: "VinFast ADAS BEV/4D Occupancy Benchmarking Lab",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased font-sans">
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-100">{children}</body>
    </html>
  );
}
