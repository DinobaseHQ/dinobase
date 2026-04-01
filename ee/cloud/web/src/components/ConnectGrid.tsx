"use client";

import type { OAuthProvider } from "@/lib/api";
import { api } from "@/lib/api";
import { useState } from "react";

export function ConnectGrid({
  providers,
  token,
}: {
  providers: OAuthProvider[];
  token: string;
}) {
  const [connecting, setConnecting] = useState<string | null>(null);

  async function handleConnect(providerName: string) {
    setConnecting(providerName);
    try {
      const redirectUri = `${window.location.origin}/connect/callback`;
      const { auth_url, state } = await api.startOAuth(
        token,
        providerName,
        redirectUri
      );
      // Store state and provider for the callback
      sessionStorage.setItem("oauth_state", state);
      sessionStorage.setItem("oauth_provider", providerName);
      // Redirect to OAuth provider
      window.location.href = auth_url;
    } catch (e) {
      setConnecting(null);
      alert(`Failed to start OAuth: ${e}`);
    }
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
      {providers.map((p) => (
        <button
          key={p.name}
          onClick={() => handleConnect(p.name)}
          disabled={!p.configured || connecting === p.name}
          className={`bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 text-sm font-medium text-left
            hover:border-dino-green hover:bg-zinc-800 transition-all
            disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-zinc-800
            ${connecting === p.name ? "opacity-60" : ""}`}
        >
          <span className="text-white">
            {p.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          </span>
          {!p.configured && (
            <span className="block text-xs text-zinc-600 mt-0.5">Soon</span>
          )}
          {connecting === p.name && (
            <span className="block text-xs text-dino-green mt-0.5">
              Connecting...
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
