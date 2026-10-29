// BFF 代理：把前端请求转发到后端并注入 X-API-Key（Key 只在服务端，不进浏览器包）
import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.HORIZON_API_BASE ?? process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";

async function proxy(request: NextRequest, path: string[]) {
  const url = `${API_BASE}/${path.join("/")}${request.nextUrl.search}`;
  const headers: Record<string, string> = { "X-API-Key": API_KEY };
  const role = request.headers.get("X-Demo-Role");
  if (role) headers["X-Demo-Role"] = role;
  let body: BodyInit | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    const contentType = request.headers.get("content-type") ?? "";
    if (contentType.includes("multipart/form-data")) {
      // 文件上传：按 multipart 原样转发，不能走 text()（会损坏二进制并丢失 boundary）
      body = await request.formData();
    } else {
      body = await request.text();
      headers["Content-Type"] = "application/json";
    }
  }
  const resp = await fetch(url, { method: request.method, headers, body, cache: "no-store" });
  const contentType = resp.headers.get("content-type") ?? "application/json";
  // 二进制响应不能走 text()（UTF-8 往返会损坏字节），直接透传
  if (contentType.includes("pdf") || contentType.includes("octet-stream") || contentType.startsWith("image/")) {
    const bytes = await resp.arrayBuffer();
    return new NextResponse(bytes, { status: resp.status, headers: { "content-type": contentType } });
  }
  const payload = await resp.text();
  return new NextResponse(payload, { status: resp.status, headers: { "content-type": contentType } });
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}
