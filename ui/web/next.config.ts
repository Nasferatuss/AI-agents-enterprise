import type { NextConfig } from "next";

// Content-Security-Policy lives in middleware.ts, not here: it needs a
// per-request nonce, because the App Router bootstraps through inline scripts
// and a static `script-src 'self'` blocks them — which left the production
// build serving a blank page. The headers below have no such requirement and
// stay static.

// `standalone` emits a self-contained server bundle for a slim Docker image.
const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
