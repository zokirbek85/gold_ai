import { type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

/**
 * SSE proxy — pipes the backend price stream directly to the browser.
 * Next.js rewrites buffer SSE; this route handler streams without buffering.
 * Browser calls /api/stream?symbol=XAUUSD → this route → backend:8001/api/v1/market-data/stream
 */
export async function GET(req: NextRequest) {
  const symbol     = req.nextUrl.searchParams.get("symbol") ?? "XAUUSD";
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8001";
  const upstreamUrl = `${backendUrl}/api/v1/market-data/stream?symbol=${symbol}`;

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      headers: { Accept: "text/event-stream", "Cache-Control": "no-cache" },
      // @ts-expect-error — Next.js / undici option to disable response buffering
      duplex: "half",
      cache: "no-store",
    });
  } catch {
    return new Response("upstream unavailable", { status: 502 });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response("stream error", { status: 502 });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type":     "text/event-stream",
      "Cache-Control":    "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      "Connection":       "keep-alive",
    },
  });
}
