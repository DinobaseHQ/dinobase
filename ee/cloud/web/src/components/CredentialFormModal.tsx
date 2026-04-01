"use client";

import { useState } from "react";
import { api, type RegistrySource } from "@/lib/api";

export function CredentialFormModal({
  source,
  token,
  existingName,
  onSuccess,
  onClose,
}: {
  source: RegistrySource;
  token: string;
  /** Set when editing an existing source — pre-fills the name field and uses update semantics. */
  existingName?: string;
  onSuccess: () => void;
  onClose: () => void;
}) {
  const isEdit = Boolean(existingName);
  const [name, setName] = useState(existingName ?? source.name);
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(source.credentials.map((c) => [c.name, ""]))
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const displayName = source.name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const trimmedName = name.trim() || (existingName ?? source.name);

      // Rename first if the name changed
      if (isEdit && existingName && trimmedName !== existingName) {
        await api.renameSource(token, existingName, trimmedName);
      }

      await api.addSource(token, {
        name: trimmedName,
        type: source.name,
        credentials: Object.fromEntries(
          Object.entries(values).map(([k, v]) => [k, v.trim()])
        ),
      });

      // Auto-trigger sync after adding or editing
      try {
        await api.triggerSync(token, trimmedName);
      } catch {
        // Sync trigger failure is non-fatal — source is already saved
      }
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  // On edit, empty fields mean "keep existing" — always allow submit
  const allFilled = isEdit || source.credentials.every((c) => values[c.name]?.trim());

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-md mx-4">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-white">{displayName}</h2>
            {source.description && (
              <p className="text-sm text-zinc-500 mt-0.5">{source.description}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-white ml-4 text-xl leading-none"
          >
            ×
          </button>
        </div>

        {source.credential_help && (
          <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-3 mb-4 text-xs text-zinc-400">
            {source.credential_help}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-sm text-zinc-300 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={source.name}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-dino-green"
              autoComplete="off"
            />
          </div>

          {source.credentials.map((cred) => (
            <div key={cred.name}>
              <label className="block text-sm text-zinc-300 mb-1">
                {cred.prompt || cred.name.replace(/_/g, " ")}
              </label>
              <input
                type={cred.secret ? "password" : "text"}
                value={values[cred.name]}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [cred.name]: e.target.value }))
                }
                placeholder={isEdit ? "leave blank to keep current" : (cred.env_var ?? undefined)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-dino-green"
                autoComplete="off"
              />
            </div>
          ))}

          {error && (
            <div className="bg-red-900/30 border border-red-800 text-red-400 text-sm px-3 py-2 rounded-lg">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !allFilled}
            className="bg-dino-green text-black font-semibold rounded-lg px-4 py-2.5 text-sm
              hover:bg-green-400 transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading
              ? isEdit ? "Saving..." : "Connecting..."
              : isEdit ? `Save ${displayName}` : `Connect ${displayName}`}
          </button>
        </form>
      </div>
    </div>
  );
}
