import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Middleware: redirect unauthenticated users away from protected routes.
 * Uses a cookie (set by the API client alongside localStorage) as a routing hint.
 */
export function middleware(request: NextRequest) {
  const token = request.cookies.get("session_token");

  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/home", "/settings", "/onboarding", "/cheat/:path*"],
};
