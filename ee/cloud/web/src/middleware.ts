import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const POSTHOG_HOST = "https://f.dinobase.ai";
const WAITLIST_URL = "https://dinobase.ai/waitlist";
const EA_COOKIE = "ea_verified";

async function hasEarlyAccess(distinctId: string): Promise<boolean> {
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!key) return true;
  try {
    const res = await fetch(`${POSTHOG_HOST}/decide/?v=3`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key, distinct_id: distinctId }),
      signal: AbortSignal.timeout(3000),
    });
    const data = await res.json();
    return !!data.featureFlags?.early_access;
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: Array<{ name: string; value: string; options?: Record<string, unknown> }>) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options as Parameters<typeof supabaseResponse.cookies.set>[2])
          );
        },
      },
    }
  );

  // Refresh the session — this is what keeps the user logged in
  const { data: { user } } = await supabase.auth.getUser();

  // Only /auth/* (OAuth/magic-link callbacks) and /cli-login (CLI auth flow) are
  // accessible without early access.
  const { pathname } = request.nextUrl;
  const isAuthRoute =
    pathname.startsWith("/auth/") || pathname.startsWith("/cli-login");

  if (isAuthRoute) {
    return supabaseResponse;
  }

  if (user) {
    // Fast path: already verified in a prior request
    if (request.cookies.get(EA_COOKIE)?.value === "1") {
      return supabaseResponse;
    }
    if (!(await hasEarlyAccess(user.email!))) {
      return NextResponse.redirect(WAITLIST_URL);
    }
    // Cache the result so subsequent requests skip the PostHog call
    supabaseResponse.cookies.set(EA_COOKIE, "1", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 3600,
      path: "/",
    });
    return supabaseResponse;
  }

  // Not logged in — allow through only if ?email= has early access
  const emailParam = request.nextUrl.searchParams.get("email");
  if (emailParam && (await hasEarlyAccess(emailParam))) {
    // Set a short-lived cookie so the check survives the OAuth redirect
    supabaseResponse.cookies.set(EA_COOKIE, "1", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 3600,
      path: "/",
    });
    return supabaseResponse;
  }

  return NextResponse.redirect(WAITLIST_URL);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
