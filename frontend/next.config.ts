import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:7061/api/:path*",
      },
      // Uploaded files (logo, attachments, measurement photos, etc.) are
      // served by FastAPI's StaticFiles mount at /uploads on the backend.
      // Proxy downloads only; browser uploads still hit the backend
      // directly to avoid Next.js body-size limits (see CLAUDE.md).
      {
        source: "/uploads/:path*",
        destination: "http://localhost:7061/uploads/:path*",
      },
    ];
  },
  async redirects() {
    return [
      {
        source: "/settings/email",
        destination: "/inbox/integrations",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
