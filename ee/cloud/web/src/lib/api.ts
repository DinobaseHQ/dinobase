const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.dinobase.ai";

export interface Source {
  name: string;
  type: string;
  auth_method: string;
  sync_interval: string;
  last_sync: string | null;
  last_sync_status: string | null;
  tables_synced: number;
  rows_synced: number;
}

export interface OAuthProvider {
  name: string;
  scopes: string[];
  configured: boolean;
}

export interface SyncStatus {
  source: string;
  type: string;
  status: string;
  last_sync: string | null;
  tables_synced: number;
  rows_synced: number;
  error: string | null;
}

export interface UserInfo {
  id: string;
  email: string;
  plan: string;
  storage_url: string;
  sources_count: number;
}

async function apiFetch<T>(
  path: string,
  token: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error (${res.status}): ${body}`);
  }
  return res.json();
}

export const api = {
  me: (token: string) => apiFetch<UserInfo>("/api/v1/auth/me", token),

  listSources: (token: string) =>
    apiFetch<Source[]>("/api/v1/sources/", token),

  addSource: (
    token: string,
    data: { name: string; type: string; credentials: Record<string, string> }
  ) =>
    apiFetch<{ name: string; type: string; status: string }>(
      "/api/v1/sources/",
      token,
      { method: "POST", body: JSON.stringify(data) }
    ),

  deleteSource: (token: string, name: string) =>
    apiFetch<{ deleted: boolean }>(`/api/v1/sources/${name}`, token, {
      method: "DELETE",
    }),

  startOAuth: (token: string, sourceName: string, redirectUri: string) =>
    apiFetch<{ auth_url: string; state: string }>(
      `/api/v1/sources/${sourceName}/auth?redirect_uri=${encodeURIComponent(redirectUri)}`,
      token,
      { method: "POST" }
    ),

  completeOAuth: (
    token: string,
    sourceName: string,
    code: string,
    redirectUri: string,
    state: string
  ) =>
    apiFetch<{ name: string; type: string; status: string }>(
      `/api/v1/sources/${sourceName}/auth/callback`,
      token,
      {
        method: "POST",
        body: JSON.stringify({ code, redirect_uri: redirectUri, state }),
      }
    ),

  triggerSync: (token: string, sourceName?: string) =>
    apiFetch<{ job_ids: string[]; status: string; sources: number }>(
      "/api/v1/sync/",
      token,
      { method: "POST", body: JSON.stringify({ source_name: sourceName }) }
    ),

  syncStatus: (token: string) =>
    apiFetch<SyncStatus[]>("/api/v1/sync/status", token),

  oauthProviders: (token: string) =>
    apiFetch<OAuthProvider[]>("/oauth/providers", token),
};
