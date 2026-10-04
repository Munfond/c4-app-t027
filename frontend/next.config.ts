import type { NextConfig } from "next";

const rawUrl = (process.env.API_INTERNAL_URL || "http://127.0.0.1:8000").trim();
const backendUrl = rawUrl.replace(/\/+$/, "").replace(/\/api$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
