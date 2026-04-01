"use client";

import type { Source, RegistrySource } from "@/lib/api";
import { api, relativeTime } from "@/lib/api";
import { useState } from "react";
import { CredentialFormModal } from "@/components/CredentialFormModal";

export function SourceCard({
  source,
  token,
  registrySource,
  onSync,
  onDelete,
}: {
  source: Source;
  token: string;
  registrySource?: RegistrySource;
  onSync: () => void;
  onDelete: () => void;
}) {
  const [syncing, setSyncing] = useState(false);
  const [editing, setEditing] = useState(false);

  async function handleSync() {
    setSyncing(true);
    try {
      const { job_ids } = await api.triggerSync(token, source.name);
      const jobId = job_ids?.[0];
      if (jobId) {
        // Poll the specific job until it finishes
        for (let i = 0; i < 60; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          const job = await api.getJob(token, jobId);
          if (job.status !== "running" && job.status !== "pending") break;
        }
      }
      onSync();
    } finally {
      setSyncing(false);
    }
  }

  const status = source.last_sync_status;
  const isError = status === "error";
  const isRunning = status === "running" || status === "pending" || syncing;

  return (
    <div className={`bg-zinc-900 border rounded-lg px-5 py-4 ${isError ? "border-red-900" : "border-zinc-800"}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <span className="font-medium text-white">{source.name}</span>
            <span className="text-zinc-500 text-sm ml-2">{source.type}</span>
          </div>
          <span
            className={`text-xs px-2 py-0.5 rounded-full ${
              source.auth_method === "oauth"
                ? "bg-green-900/50 text-green-400"
                : "bg-blue-900/50 text-blue-400"
            }`}
          >
            {source.auth_method}
          </span>
          {source.updated_at && (
            <span className="text-xs text-zinc-600">
              edited {relativeTime(source.updated_at)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <div className="text-sm text-right">
            {isRunning ? (
              <span className="text-dino-green animate-pulse">Syncing...</span>
            ) : isError ? (
              <span className="text-red-400">Sync failed</span>
            ) : source.last_sync ? (
              <div>
                <span className="text-zinc-500">
                  {source.tables_synced} tables, {source.rows_synced.toLocaleString()} rows
                </span>
                {source.sync_interval && source.sync_interval !== "manual" && (
                  <div className="text-zinc-600 text-xs mt-0.5">
                    auto-syncs every {source.sync_interval}
                  </div>
                )}
              </div>
            ) : (
              <span className="text-zinc-600">Not synced</span>
            )}
          </div>
          <button
            onClick={handleSync}
            disabled={isRunning}
            className="text-xs text-zinc-400 hover:text-white border border-zinc-700 px-3 py-1.5 rounded-md hover:border-zinc-500 disabled:opacity-50"
          >
            {isRunning ? "Syncing..." : "Sync"}
          </button>
          {registrySource && (
            <button
              onClick={() => setEditing(true)}
              className="text-xs text-zinc-600 hover:text-zinc-300"
            >
              Edit
            </button>
          )}
          <button
            onClick={onDelete}
            className="text-xs text-zinc-600 hover:text-red-400"
          >
            Remove
          </button>
        </div>
      </div>
      {editing && registrySource && (
        <CredentialFormModal
          source={registrySource}
          token={token}
          existingName={source.name}
          onSuccess={() => { setEditing(false); onSync(); }}
          onClose={() => setEditing(false)}
        />
      )}
      {isError && !syncing && source.last_sync_error && (
        <div className="mt-3 text-xs text-red-400 bg-red-950/40 border border-red-900/50 rounded px-3 py-2 flex items-start justify-between gap-3">
          <span>{source.last_sync_error}</span>
          {source.last_sync_error.includes("Edit credentials") && registrySource && (
            <button
              onClick={() => setEditing(true)}
              className="text-red-300 hover:text-white underline shrink-0"
            >
              Edit credentials
            </button>
          )}
        </div>
      )}
    </div>
  );
}
