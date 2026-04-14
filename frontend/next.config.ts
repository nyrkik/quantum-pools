import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:7061/api/:path*",
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
