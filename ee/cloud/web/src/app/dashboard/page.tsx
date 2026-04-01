"use client";

import { createClient } from "@/lib/supabase";
import { api, type Source, type OAuthProvider } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { SourceCard } from "@/components/SourceCard";
import { ConnectGrid } from "@/components/ConnectGrid";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";

export default function DashboardPage() {
  const supabase = createClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const connected = searchParams.get("connected");

  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [providers, setProviders] = useState<OAuthProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [showToken, setShowToken] = useState(false);

  const loadData = useCallback(
    async (accessToken: string) => {
      try {
        const [s, p] = await Promise.all([
          api.listSources(accessToken),
          api.oauthProviders(accessToken),
        ]);
        setSources(s);
        setProviders(p);
      } catch (e) {
        console.error("Failed to load data:", e);
      }
    },
    []
  );

  useEffect(() => {
    // Use getUser() first (validates with Supabase server), then getSession() for the token
    supabase.auth.getUser().then(({ data: { user }, error }) => {
      if (error || !user) {
        router.replace("/login");
        return;
      }
      setEmail(user.email || "");
      // Now get the session for the access token
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setToken(session.access_token);
        loadData(session.access_token).then(() => setLoading(false));
      });
    });
  }, []);

  async function handleDelete(name: string) {
    if (!confirm(`Remove source "${name}"?`)) return;
    await api.deleteSource(token, name);
    loadData(token);
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-4xl animate-pulse">&#x1F995;</div>
      </div>
    );
  }

  return (
    <>
      <Nav email={email} />
      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Flash message for successful connection */}
        {connected && (
          <div className="bg-green-900/30 border border-green-800 text-green-400 px-4 py-3 rounded-lg mb-6 text-sm">
            Connected <strong>{connected}</strong> successfully.
          </div>
        )}

        <h1 className="text-2xl font-bold mb-8">Dashboard</h1>

        {/* Connected Sources */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4 text-zinc-300">
            Connected sources
          </h2>
          {sources.length > 0 ? (
            <div className="flex flex-col gap-3">
              {sources.map((s) => (
                <SourceCard
                  key={s.name}
                  source={s}
                  token={token}
                  onSync={() => loadData(token)}
                  onDelete={() => handleDelete(s.name)}
                />
              ))}
            </div>
          ) : (
            <div className="bg-zinc-900 border border-zinc-800 border-dashed rounded-lg px-5 py-10 text-center text-zinc-500">
              No sources connected yet. Connect one below.
            </div>
          )}
        </section>

        {/* Connect New Source */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-2 text-zinc-300">
            Connect a source
          </h2>
          <p className="text-sm text-zinc-500 mb-4">
            Click to authorize via OAuth. No API keys needed.
          </p>
          <ConnectGrid providers={providers} token={token} />
        </section>

        {/* CLI Setup */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4 text-zinc-300">
            CLI setup
          </h2>
          <pre className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 text-sm overflow-x-auto">
            <code className="text-dino-green">
              {`pip install dinobase\ndinobase login`}
            </code>
          </pre>

          <div className="mt-4">
            <button
              onClick={() => setShowToken(!showToken)}
              className="text-sm text-zinc-500 hover:text-zinc-300"
            >
              {showToken ? "Hide" : "Show"} access token
            </button>
            {showToken && (
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mt-2 flex items-center justify-between">
                <code className="text-dino-green text-xs break-all">
                  {token}
                </code>
                <button
                  onClick={() => navigator.clipboard.writeText(token)}
                  className="text-zinc-500 hover:text-white text-xs ml-4 shrink-0"
                >
                  Copy
                </button>
              </div>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
