import type { NextConfig } from "next";

// BACKEND_URL is a server-only build-time variable that tells the Next.js
// rewrite proxy where to forward /api/* requests. It must point to the
// backend as seen FROM the frontend container (i.e. the Docker service name),
// not from the user's browser. Never use NEXT_PUBLIC_ here.
const backendUrl = process.env.BACKEND_URL || "http://localhost:8001";

const nextConfig: NextConfig = {
  output: "standalone",
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
