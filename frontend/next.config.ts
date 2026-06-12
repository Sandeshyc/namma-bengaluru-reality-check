import type { NextConfig } from "next";
import path from "path";
import { loadEnvConfig } from "@next/env";

// Monorepo: `.env` lives at repo root. Next.js 16 does not support `envDir` here;
// load parent `.env*` into `process.env` before the dev server / build reads config.
const repoRoot = path.resolve(__dirname, "..");
loadEnvConfig(repoRoot, process.env.NODE_ENV !== "production", undefined, true);

const nextConfig: NextConfig = {};

export default nextConfig;
