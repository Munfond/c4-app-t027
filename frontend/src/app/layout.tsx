import type { Metadata } from "next";
import { AppShell } from "@/components/shell/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "ADAS Perception Lab",
    template: "%s · ADAS Perception Lab",
  },
  description:
    "Không gian trực quan hóa và so sánh kết quả mô hình nhận thức ADAS.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
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
