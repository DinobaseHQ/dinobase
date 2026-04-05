"use client";

import { Suspense } from "react";
import { createClient } from "@/lib/supabase";
import { api } from "@/lib/api";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

function ConnectCallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleCallback() {
      const code = searchParams.get("code");
      const state = searchParams.get("state");
      const oauthError = searchParams.get("error");

      if (oauthError) {
        setError(oauthError);
        return;
      }
      if (!code) {
        setError("No authorization code received");
        return;
      }

      // Retrieve stored state and provider
      const expectedState = sessionStorage.getItem("oauth_state");
      const provider = sessionStorage.getItem("oauth_provider");

      if (!provider) {
        setError("No provider found in session. Please try connecting again.");
        return;
      }
      if (state !== expectedState) {
        setError("State mismatch. Please try connecting again.");
        return;
      }

      // Get the access token
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        router.replace("/login");
        return;
      }

      try {
        const redirectUri = `${window.location.origin}/connect/callback`;
        await api.completeOAuth(
          session.access_token,
          provider,
          code,
          redirectUri,
          state || ""
        );

        // Clean up
        sessionStorage.removeItem("oauth_state");
        sessionStorage.removeItem("oauth_provider");

        // Redirect to dashboard with success
        router.replace(`/dashboard?connected=${provider}`);
      } catch (e) {
        setError(`Failed to complete connection: ${e}`);
      }
    }

    handleCallback();
  }, []);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-zinc-900 border border-red-800 rounded-xl p-8 max-w-md text-center">
          <div className="text-4xl mb-4">&#x26A0;&#xFE0F;</div>
          <h2 className="text-lg font-semibold mb-2 text-red-400">
            Connection failed
          </h2>
          <p className="text-zinc-400 text-sm mb-4">{error}</p>
          <button
            onClick={() => router.push("/dashboard")}
            className="bg-zinc-800 text-white px-6 py-2 rounded-lg text-sm hover:bg-zinc-700"
          >
            Back to dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="text-4xl mb-4 animate-pulse">&#x1F517;</div>
        <p className="text-zinc-400">Connecting your account...</p>
      </div>
    </div>
  );
}

export default function ConnectCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-4xl animate-pulse">&#x1F995;</div>
        </div>
      }
    >
      <ConnectCallbackInner />
    </Suspense>
  );
}
