"use client";

import { Suspense } from "react";
import { createClient } from "@/lib/supabase";
import { Nav } from "@/components/Nav";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

function CLILoginInner() {
  const supabase = createClient();
  const searchParams = useSearchParams();

  const callback = searchParams.get("callback");
  const state = searchParams.get("state");

  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [redirecting, setRedirecting] = useState(false);

  // Check if already logged in — redirect to CLI immediately
  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user) {
        redirectToCLI();
      }
    });
  }, []);

  // Listen for auth state changes (fires after OAuth redirect back)
  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_IN" && session) {
        redirectToCLI();
      }
    });
    return () => subscription.unsubscribe();
  }, []);

  async function redirectToCLI() {
    if (!callback) return;
    setRedirecting(true);

    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) return;

    // Send tokens back to the CLI's local callback server. The webapp
    // dashboard is gated separately by `early_access` in middleware.ts;
    // CLI login must always complete so that source OAuth works even for
    // users who are still on the waitlist for webapp access.
    const params = new URLSearchParams({
      access_token: session.access_token,
      refresh_token: session.refresh_token || "",
      expires_at: String(session.expires_at || 0),
      user_id: session.user.id,
      email: session.user.email || "",
      state: state || "",
    });

    window.location.href = `${callback}?${params.toString()}`;
  }

  // Route Supabase back through /auth/callback (which exchanges the PKCE
  // code for a session) and have it forward to /cli-login afterwards via
  // its `next` param, preserving the CLI's callback URL and state.
  function authCallbackUrl(): string {
    const next = `/cli-login?callback=${encodeURIComponent(callback || "")}&state=${encodeURIComponent(state || "")}`;
    return `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;
  }

  async function handleMagicLink(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: authCallbackUrl() },
    });
    setLoading(false);
    if (error) {
      alert(error.message);
    } else {
      setSent(true);
    }
  }

  async function handleGitHub() {
    await supabase.auth.signInWithOAuth({
      provider: "github",
      options: { redirectTo: authCallbackUrl() },
    });
  }

  async function handleGoogle() {
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: authCallbackUrl() },
    });
  }

  if (redirecting) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <div className="text-center">
          <div className="text-4xl mb-4 animate-pulse">&#x1F995;</div>
          <p className="text-zinc-400">Sending credentials to CLI...</p>
          <p className="text-zinc-600 text-sm mt-2">
            You can close this tab after the terminal confirms.
          </p>
        </div>
      </div>
    );
  }

  if (!callback) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <div className="text-center">
          <p className="text-zinc-400">
            This page is for CLI login. Run{" "}
            <code className="bg-zinc-800 px-2 py-1 rounded">dinobase login</code>{" "}
            in your terminal.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <Nav showAuth={false} />
      <main className="max-w-md mx-auto px-6 py-24">
        <h1 className="text-3xl font-bold mb-2 text-center">
          Sign in to Dinobase
        </h1>
        <p className="text-zinc-400 text-center mb-8">
          Authenticate to connect your CLI
        </p>

        {sent ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center">
            <div className="text-4xl mb-4">&#x2709;&#xFE0F;</div>
            <h2 className="text-lg font-semibold mb-2">Check your email</h2>
            <p className="text-zinc-400 text-sm">
              We sent a sign-in link to{" "}
              <span className="text-white font-medium">{email}</span>
            </p>
          </div>
        ) : (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8">
            <div className="flex flex-col gap-3 mb-6">
              <button
                onClick={handleGitHub}
                className="border border-zinc-700 rounded-lg px-4 py-3 text-sm font-medium hover:border-zinc-500 flex items-center justify-center gap-2"
              >
                <svg
                  className="w-5 h-5"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                </svg>
                Continue with GitHub
              </button>
              <button
                onClick={handleGoogle}
                className="border border-zinc-700 rounded-lg px-4 py-3 text-sm font-medium hover:border-zinc-500 flex items-center justify-center gap-2"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg>
                Continue with Google
              </button>
            </div>

            <div className="flex items-center gap-4 mb-6">
              <div className="flex-1 h-px bg-zinc-800" />
              <span className="text-xs text-zinc-500">OR</span>
              <div className="flex-1 h-px bg-zinc-800" />
            </div>

            <form onSubmit={handleMagicLink}>
              <label className="block text-sm text-zinc-400 mb-2">
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 text-sm placeholder:text-zinc-600 focus:border-dino-green focus:outline-none mb-4"
              />
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-dino-green text-white py-3 rounded-lg text-sm font-medium hover:brightness-110 disabled:opacity-50"
              >
                {loading ? "Sending..." : "Send magic link"}
              </button>
            </form>
          </div>
        )}
      </main>
    </>
  );
}

export default function CLILoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-4xl animate-pulse">&#x1F995;</div>
        </div>
      }
    >
      <CLILoginInner />
    </Suspense>
  );
}
