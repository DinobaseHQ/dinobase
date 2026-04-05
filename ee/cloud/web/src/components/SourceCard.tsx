"use client";

import type { Source, RegistrySource } from "@/lib/api";
import { api, relativeTime } from "@/lib/api";
import { useState, useEffect } from "react";
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
  const [syncProgress, setSyncProgress] = useState<{
    current: number;
    total: number;
  } | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);

  async function pollJob(jobId: string) {
    setCurrentJobId(jobId);
    try {
      for (let i = 0; i < 300; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const job = await api.getJob(token, jobId);
        if (job.tables_synced > 0 || job.tables_total > 0) {
          setSyncProgress({
            current: job.tables_synced,
            total: job.tables_total,
          });
        }
        if (job.status !== "running" && job.status !== "pending") break;
      }
    } finally {
      setCurrentJobId(null);
    }
  }

  async function handleStop() {
    if (!currentJobId) return;
    try {
      await api.cancelJob(token, currentJobId);
    } catch {
      // Poll loop will exit naturally on the next tick when it sees non-running status
    }
  }

  // Resume progress display if the backend is already syncing when we mount
  // (e.g. after a page reload mid-sync).
  useEffect(() => {
    if (
      (source.last_sync_status === "running" ||
        source.last_sync_status === "pending") &&
      source.last_job_id
    ) {
      setSyncing(true);
      pollJob(source.last_job_id)
        .then(() => onSync())
        .finally(() => {
          setSyncing(false);
          setSyncProgress(null);
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSync() {
    setSyncing(true);
    setSyncProgress(null);
    try {
      const { job_ids } = await api.triggerSync(token, source.name);
      const jobId = job_ids?.[0];
      if (jobId) {
        await pollJob(jobId);
      }
      onSync();
    } finally {
      setSyncing(false);
      setSyncProgress(null);
    }
  }

  const status = source.last_sync_status;
  const isError = status === "error";
  const isRunning = status === "running" || status === "pending" || syncing;

  return (
    <div
      className={`bg-zinc-900 border rounded-lg px-5 py-4 ${isError && !isRunning ? "border-red-900" : "border-zinc-800"}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <span className="font-medium text-white">{source.name}</span>
            <span className="text-zinc-500 text-sm ml-2">{source.type}</span>
          </div>
          {source.updated_at && (
            <span className="text-xs text-zinc-600">
              edited {relativeTime(source.updated_at)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <div className="text-sm text-right">
            {isRunning ? (
              <div className="text-right">
                <span className="text-dino-green animate-pulse">
                  {syncProgress
                    ? syncProgress.total > 0
                      ? syncProgress.total === syncProgress.current
                        ? "Finalizing sync"
                        : `Syncing... ${syncProgress.current}/${syncProgress.total} tables`
                      : `Syncing... ${syncProgress.current} tables`
                    : "Preparing sync..."}
                </span>
                {syncProgress && syncProgress.total > 0 && (
                  <div className="mt-1 w-36 bg-zinc-800 rounded-full h-1 ml-auto">
                    <div
                      className="bg-dino-green h-1 rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.min((syncProgress.current / syncProgress.total) * 100, 100)}%`,
                      }}
                    />
                  </div>
                )}
              </div>
            ) : isError ? (
              <span className="text-red-400">Sync failed</span>
            ) : source.last_sync ? (
              <div>
                <span className="text-zinc-500">
                  {source.tables_synced} tables,{" "}
                  {source.rows_synced.toLocaleString()} rows
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
          {!isRunning && (
            <button
              onClick={handleSync}
              disabled={isRunning}
              className="text-xs text-zinc-400 hover:text-white border border-zinc-700 px-3 py-1.5 rounded-md hover:border-zinc-500 disabled:opacity-50"
            >
              Sync
            </button>
          )}
          {isRunning && currentJobId && (
            <button
              onClick={handleStop}
              className="text-xs text-zinc-500 hover:text-red-400 border border-zinc-700 px-3 py-1.5 rounded-md hover:border-red-800"
            >
              Stop
            </button>
          )}
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
          onSuccess={() => {
            setEditing(false);
            onSync();
          }}
          onClose={() => setEditing(false)}
        />
      )}
      {isError && !syncing && source.last_sync_error && (
        <div className="mt-3 text-xs text-red-400 bg-red-950/40 border border-red-900/50 rounded px-3 py-2 flex items-start justify-between gap-3">
          <span>{source.last_sync_error}</span>
          {source.last_sync_error.includes("Edit credentials") &&
            registrySource && (
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
