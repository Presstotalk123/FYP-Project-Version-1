import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'export',  // Add this line for static export
  images: {
    unoptimized: true,  // Required for static export
  },
};

export default nextConfig;
