const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.dinobase.ai";

export interface Source {
  name: string;
  type: string;
  auth_method: string;
  sync_interval: string;
  updated_at: string | null;
  last_sync: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  last_job_id: string | null;
  tables_synced: number;
  rows_synced: number;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
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

export interface CredentialParam {
  name: string;
  cli_flag: string;
  env_var: string | null;
  prompt: string | null;
  secret: boolean;
}

export interface RegistrySource {
  name: string;
  description: string;
  category: "api" | "database" | "file_storage";
  supports_oauth: boolean;
  oauth_configured: boolean;
  credential_help: string | null;
  credentials: CredentialParam[];
  pip_extra: string | null;
}

export interface UserInfo {
  id: string;
  email: string;
  plan: string;
  storage_url: string;
  sources_count: number;
}

export interface SandboxInfo {
  sources: Array<{
    name: string;
    tables: Array<{ name: string; rows: number }>;
    table_count: number;
    total_rows: number;
  }>;
  suggested_questions: string[];
  models: string[];
  default_model: string;
}

export interface SandboxRunRequest {
  question: string;
  model: string;
  expected_answer?: string;
}

export type SandboxEvent =
  | {
      type: "turn";
      approach: "dinobase" | "mcp";
      role: "assistant" | "tool" | "tool_result";
      text?: string;
      tool?: string;
      input?: Record<string, unknown>;
      output?: string;
    }
  | {
      type: "metric";
      approach: "dinobase" | "mcp";
      tokens_in: number;
      tokens_out: number;
      latency_ms: number;
      tool_calls: number;
      turns: number;
    }
  | {
      type: "score";
      approach: "dinobase" | "mcp";
      correct: boolean;
      partial: boolean;
      explanation: string;
    }
  | { type: "done" }
  | { type: "error"; approach?: string; message: string };

export interface QueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
  data_types?: Record<string, string>;
  row_count: number;
}

export interface SourceTable {
  name: string;
  rows: number;
}

export interface SchemaSource {
  name: string;
  tables: SourceTable[];
  table_count: number;
  total_rows: number;
  last_sync: string | null;
}

export interface SchemaTree {
  sources: SchemaSource[];
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

  renameSource: (token: string, oldName: string, newName: string) =>
    apiFetch<{ name: string }>(`/api/v1/sources/${oldName}/rename`, token, {
      method: "PATCH",
      body: JSON.stringify({ new_name: newName }),
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

  cancelJob: (token: string, jobId: string) =>
    apiFetch<{ cancelled: boolean }>(`/api/v1/sync/jobs/${jobId}/cancel`, token, {
      method: "POST",
    }),

  getJob: (token: string, jobId: string) =>
    apiFetch<{
      job_id: string;
      source: string;
      status: string;
      tables_synced: number;
      tables_total: number;
      rows_synced: number;
      error: string | null;
    }>(`/api/v1/sync/jobs/${jobId}`, token),

  oauthProviders: (token: string) =>
    apiFetch<OAuthProvider[]>("/oauth/providers", token),

  sourceRegistry: (token: string) =>
    apiFetch<{ sources: RegistrySource[] }>("/api/v1/sources/registry", token),

  query: (token: string, sql: string, maxRows = 500) =>
    apiFetch<QueryResult>("/api/v1/query/", token, {
      method: "POST",
      body: JSON.stringify({ sql, max_rows: maxRows }),
    }),

  tables: (token: string) =>
    apiFetch<SchemaTree>("/api/v1/query/tables", token),

  describe: (token: string, table: string) =>
    apiFetch<Record<string, unknown>>(`/api/v1/query/describe/${encodeURIComponent(table)}`, token),

  getSandboxInfo: (token: string) =>
    apiFetch<SandboxInfo>("/api/v1/sandbox/", token),

  streamSandbox: async function* (
    token: string,
    body: SandboxRunRequest
  ): AsyncGenerator<SandboxEvent> {
    const res = await fetch(`${API_URL}/api/v1/sandbox/run`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Sandbox error (${res.status}): ${text}`);
    }

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            yield JSON.parse(line.slice(6)) as SandboxEvent;
          } catch {
            // skip malformed lines
          }
        }
      }
    }
  },
};
