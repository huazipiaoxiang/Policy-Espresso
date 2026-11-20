/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // 同一目录同时跑多个 dev 实例时必须隔离构建产物，否则共享 .next 会互相覆盖，
  // 导致代理路由 404、chunk 失效、登录后跳转卡死。
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
