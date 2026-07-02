import type { NextConfig } from "next";

// The demo console talks to the gateway at NEXT_PUBLIC_API_URL (baked at build).
// CSP must allow XHR/fetch to that origin, so derive connect-src from it.
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const isDev = process.env.NODE_ENV !== "production";

// Content-Security-Policy: lock the app to same-origin resources + the API origin.
// Dev needs 'unsafe-eval' for React Fast Refresh / HMR; production does not, so we
// only relax it there. 'unsafe-inline' on style-src covers Tailwind/inline styles.
const csp = [
  "default-src 'self'",
  `script-src 'self'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  `connect-src 'self' ${apiUrl}${isDev ? " ws:" : ""}`,
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
].join("; ");

// `standalone` emits a self-contained server bundle for a slim Docker image.
const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
