"use client";

import { useState } from "react";
import type { SchemaTree } from "@/lib/api";

interface SchemaPanelProps {
  schema: SchemaTree | null;
  loading: boolean;
  onTableClick: (schema: string, table: string) => void;
}

export function SchemaPanel({ schema, loading, onTableClick }: SchemaPanelProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  function toggle(name: string) {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  if (loading) {
    return (
      <div className="p-4 text-zinc-600 text-sm">Loading schema…</div>
    );
  }

  if (!schema || schema.sources.length === 0) {
    return (
      <div className="p-4 text-zinc-600 text-sm">
        No sources synced yet. Connect a source on the{" "}
        <a href="/dashboard" className="text-dino-green hover:underline">Dashboard</a>.
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full py-2">
      {schema.sources.map((source) => {
        const isOpen = expanded[source.name] ?? true;
        return (
          <div key={source.name} className="mb-1">
            <button
              onClick={() => toggle(source.name)}
              className="w-full flex items-center gap-1.5 px-3 py-1.5 text-left hover:bg-zinc-800/50 transition-colors group"
            >
              <span className="text-zinc-500 text-xs w-3 flex-shrink-0">
                {isOpen ? "▾" : "▸"}
              </span>
              <span className="text-zinc-300 text-sm font-medium truncate">{source.name}</span>
              <span className="ml-auto text-xs text-zinc-600 flex-shrink-0">{source.table_count}</span>
            </button>
            {isOpen && (
              <div className="ml-4">
                {source.tables.map((t) => (
                  <button
                    key={t.name}
                    onClick={() => onTableClick(source.name, t.name)}
                    className="w-full flex items-center gap-2 px-3 py-1 text-left hover:bg-zinc-800/60 transition-colors rounded"
                  >
                    <span className="text-zinc-500 text-xs">⊞</span>
                    <span className="text-zinc-400 text-xs truncate">{t.name}</span>
                    <span className="ml-auto text-[10px] text-zinc-600 flex-shrink-0">
                      {t.rows.toLocaleString()}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
