import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,  // Required for static export
  },
};

export default nextConfig;
