import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public pages and Next.js internals
  if (
    PUBLIC_PATHS.some(p => pathname.startsWith(p)) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname === "/favicon.ico"
  ) {
    return NextResponse.next();
  }

  // Check for access token in cookies (set on login) or allow through
  // Token is stored in localStorage (client-only), so middleware can't
  // read it. We protect at the component level instead via the auth store.
  // Middleware only handles server-set cookies here for SSR cases.
  const token = request.cookies.get("access_token")?.value;

  // If no cookie token, let client-side auth guard handle it
  // (avoids redirect loop for localStorage-based auth)
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
