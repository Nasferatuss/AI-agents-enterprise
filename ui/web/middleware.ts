import { NextRequest, NextResponse } from "next/server";

// Content-Security-Policy is set here rather than in next.config.ts because it
// needs a per-request nonce.
//
// The App Router bootstraps and streams the RSC payload through inline
// <script> tags (`self.__next_f.push(...)`). A static `script-src 'self'`
// blocks every one of them: the server-rendered HTML still arrives, but
// hydration dies and React tears the tree down, so the console renders as a
// blank page. That is what the production Docker image used to serve.
//
// The fix is a nonce, not 'unsafe-inline' — 'unsafe-inline' would let any
// injected inline script run, which is the thing the policy exists to stop.
// Next.js reads the nonce out of the Content-Security-Policy header on the
// *request* and stamps it onto the scripts it emits, so both headers below are
// deliberate: one for Next, one for the browser.
//
// 'strict-dynamic' lets those nonced bootstrap scripts load the chunk scripts
// they need without every chunk URL having to be enumerated.
//
// Cost of this: a request carrying a fresh nonce cannot be served from the
// static prerender cache, so these pages render dynamically. For a demo console
// backed by a live API that is the correct trade — the alternative was a page
// that did not work at all.

export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const isDev = process.env.NODE_ENV !== "production";

  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    `connect-src 'self' ${apiUrl}${isDev ? " ws:" : ""}`,
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    // Everything except Next's own static assets and the favicon: those are
    // plain files, they carry no inline script, and giving each one a unique
    // nonce would only defeat caching.
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
