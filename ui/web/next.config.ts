import type { NextConfig } from "next";

// `standalone` emits a self-contained server bundle for a slim Docker image.
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
