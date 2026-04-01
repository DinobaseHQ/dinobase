"use client";

import type { Source } from "@/lib/api";
import { api } from "@/lib/api";
import { useState } from "react";

export function SourceCard({
  source,
  token,
  onSync,
  onDelete,
}: {
  source: Source;
  token: string;
  onSync: () => void;
  onDelete: () => void;
}) {
  const [syncing, setSyncing] = useState(false);

  async function handleSync() {
    setSyncing(true);
    try {
      await api.triggerSync(token, source.name);
      onSync();
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-5 py-4 flex items-center justify-between">
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
      </div>
      <div className="flex items-center gap-4">
        <div className="text-sm text-zinc-500 text-right">
          {source.last_sync ? (
            <>
              {source.tables_synced} tables, {source.rows_synced.toLocaleString()}{" "}
              rows
            </>
          ) : (
            "Not synced"
          )}
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="text-xs text-zinc-400 hover:text-white border border-zinc-700 px-3 py-1.5 rounded-md hover:border-zinc-500 disabled:opacity-50"
        >
          {syncing ? "Syncing..." : "Sync"}
        </button>
        <button
          onClick={onDelete}
          className="text-xs text-zinc-600 hover:text-red-400"
        >
          Remove
        </button>
      </div>
    </div>
  );
}
