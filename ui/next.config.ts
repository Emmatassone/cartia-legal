import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // `standalone` produce un server mínimo para el contenedor que corre en Tilt.
  // Vercel ignora esta opción y usa su propio pipeline.
  output: process.env.NEXT_OUTPUT_STANDALONE === "true" ? "standalone" : undefined,
};

export default nextConfig;
