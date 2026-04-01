"use client";

import { createClient } from "@/lib/supabase";
import { api, type Source, type OAuthProvider, type RegistrySource } from "@/lib/api";
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
  const [registrySources, setRegistrySources] = useState<RegistrySource[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(
    async (accessToken: string) => {
      try {
        await api.me(accessToken); // ensures user profile exists before any sync
        const [s, p] = await Promise.all([
          api.listSources(accessToken),
          api.oauthProviders(accessToken),
        ]);
        setSources(s);
        setProviders(p);
      } catch (e) {
        console.error("Failed to load data:", e);
      }
      try {
        const reg = await api.sourceRegistry(accessToken);
        setRegistrySources(reg.sources);
      } catch (e) {
        console.error("Failed to load source registry:", e);
      }
    },
    []
  );

  useEffect(() => {
    // Subscribe to auth state changes so the token stays fresh across refreshes.
    // Supabase auto-refreshes the JWT before expiry and fires TOKEN_REFRESHED here.
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        const freshToken = session.access_token;
        setEmail(session.user.email ?? "");
        setToken(freshToken);
        if (event === "INITIAL_SESSION" || event === "SIGNED_IN") {
          loadData(freshToken).then(() => setLoading(false));
        }
      }
    );
    return () => subscription.unsubscribe();
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
                  registrySource={registrySources.find((r) => r.name === s.type)}
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
          <h2 className="text-lg font-semibold mb-4 text-zinc-300">
            Connect a source
          </h2>
          <ConnectGrid
            registrySources={registrySources}
            providers={providers}
            token={token}
            onSourceAdded={() => loadData(token)}
          />
        </section>

      </main>
    </>
  );
}
