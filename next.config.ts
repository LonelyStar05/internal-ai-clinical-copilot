import type { NextConfig } from "next";

// Frontend gọi /api/... ; Next chuyển tiếp sang backend FastAPI (mặc định cổng 8000).
// Dùng IPv4 rõ ràng vì trên Windows `localhost` có thể ưu tiên ::1,
// trong khi Uvicorn mặc định chỉ lắng nghe trên 127.0.0.1.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
