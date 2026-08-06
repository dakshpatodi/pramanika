import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  images: {
    // Add allowed remote image hosts here as real product photography
    // is introduced in later phases (e.g. a CMS or S3/CDN domain).
    remotePatterns: [],
  },
};

export default nextConfig;
