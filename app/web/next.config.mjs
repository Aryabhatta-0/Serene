import { pageExtensions } from "./fixture-routes.mjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  pageExtensions: pageExtensions(),
};

export default nextConfig;
