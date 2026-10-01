import type { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "P-027 Perception Lab",
    template: "%s · ADAS Perception Lab",
  },
  description: "VinFast ADAS BEV/4D Occupancy Benchmarking Lab",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="min-h-full">
        <a className="skip-link" href="#main-content">
          Đi tới nội dung chính
        </a>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
