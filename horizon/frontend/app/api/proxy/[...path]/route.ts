// BFF 代理：把前端请求转发到后端并注入 X-API-Key（Key 只在服务端，不进浏览器包）
import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";

async function proxy(request: NextRequest, path: string[]) {
  const url = `${API_BASE}/${path.join("/")}${request.nextUrl.search}`;
  const headers: Record<string, string> = { "X-API-Key": API_KEY };
  let body: string | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.text();
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(url, { method: request.method, headers, body, cache: "no-store" });
  const contentType = resp.headers.get("content-type") ?? "application/json";
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
