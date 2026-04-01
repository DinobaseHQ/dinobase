"use client";

import { useState } from "react";
import { api, type OAuthProvider, type RegistrySource } from "@/lib/api";
import { CredentialFormModal } from "@/components/CredentialFormModal";

type Category = "api" | "database" | "file_storage";

const CATEGORY_LABELS: Record<Category, string> = {
  api: "APIs",
  database: "Databases",
  file_storage: "File Storage",
};

export function ConnectGrid({
  registrySources,
  providers,
  token,
  onSourceAdded,
}: {
  registrySources: RegistrySource[];
  providers: OAuthProvider[];
  token: string;
  onSourceAdded: () => void;
}) {
  const [activeCategory, setActiveCategory] = useState<Category>("api");
  const [search, setSearch] = useState("");
  const [connecting, setConnecting] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<RegistrySource | null>(null);

  const filtered = registrySources.filter(
    (s) =>
      s.category === activeCategory &&
      s.name.replace(/_/g, " ").toLowerCase().includes(search.toLowerCase())
  );

  async function handleOAuth(sourceName: string) {
    setConnecting(sourceName);
    try {
      const redirectUri = `${window.location.origin}/connect/callback`;
      const { auth_url, state } = await api.startOAuth(token, sourceName, redirectUri);
      sessionStorage.setItem("oauth_state", state);
      sessionStorage.setItem("oauth_provider", sourceName);
      window.location.href = auth_url;
    } catch (e) {
      setConnecting(null);
      alert(`Failed to start OAuth: ${e}`);
    }
  }

  function handleClick(source: RegistrySource) {
    if (source.oauth_configured) {
      handleOAuth(source.name);
    } else {
      setSelectedSource(source);
    }
  }

  return (
    <>
      {/* Category tabs */}
      <div className="flex gap-1 border-b border-zinc-800 mb-4">
        {(["api", "database", "file_storage"] as Category[]).map((cat) => (
          <button
            key={cat}
            onClick={() => { setActiveCategory(cat); setSearch(""); }}
            className={`px-4 py-2 text-sm font-medium transition-colors
              ${activeCategory === cat
                ? "border-b-2 border-dino-green text-white -mb-px"
                : "text-zinc-500 hover:text-zinc-300"
              }`}
          >
            {CATEGORY_LABELS[cat]}
          </button>
        ))}
      </div>

      {/* Search */}
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={`Search ${CATEGORY_LABELS[activeCategory].toLowerCase()}...`}
        className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-zinc-600 mb-4"
      />

      {/* Grid */}
      {filtered.length === 0 && search ? (
        <p className="text-sm text-zinc-600 py-4">No results for &quot;{search}&quot;</p>
      ) : filtered.length === 0 ? null : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {filtered.map((source) => {
            const displayName = source.name
              .replace(/_/g, " ")
              .replace(/\b\w/g, (c) => c.toUpperCase());
            const isConnecting = connecting === source.name;

            return (
              <div key={source.name} className="flex flex-col gap-1">
                <button
                  onClick={() => handleClick(source)}
                  disabled={isConnecting}
                  className={`bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 text-sm font-medium text-left
                    hover:border-dino-green hover:bg-zinc-800 transition-all
                    disabled:opacity-60 disabled:cursor-not-allowed
                    ${isConnecting ? "opacity-60" : ""}`}
                >
                  <span className="text-white block truncate">{displayName}</span>
                  {source.oauth_configured && (
                    <span className="text-xs text-dino-green mt-0.5 block">OAuth</span>
                  )}
                  {isConnecting && (
                    <span className="text-xs text-dino-green mt-0.5 block">Connecting...</span>
                  )}
                </button>
                {source.supports_oauth && source.oauth_configured && (
                  <button
                    onClick={() => setSelectedSource(source)}
                    className="text-xs text-zinc-600 hover:text-zinc-400 text-left px-1"
                  >
                    Use API key
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Credential form modal */}
      {selectedSource && (
        <CredentialFormModal
          source={selectedSource}
          token={token}
          onSuccess={() => {
            setSelectedSource(null);
            onSourceAdded();
          }}
          onClose={() => setSelectedSource(null)}
        />
      )}
    </>
  );
}
