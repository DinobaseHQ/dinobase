"use client";

import { createClient } from "@/lib/supabase";
import { api, type QueryResult, type SchemaTree } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { SqlEditor } from "@/components/SqlEditor";
import { ResultTable } from "@/components/ResultTable";
import { SchemaPanel } from "@/components/SchemaPanel";
import { QueryChart, canChart } from "@/components/QueryChart";
import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback } from "react";

type ViewMode = "table" | "chart";

export default function QueryPage() {
  const supabase = createClient();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [authLoading, setAuthLoading] = useState(true);

  const [sql, setSql] = useState("SELECT 1 AS value");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("table");

  const [schema, setSchema] = useState<SchemaTree | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);

  const loadSchema = useCallback(async (accessToken: string) => {
    setSchemaLoading(true);
    try {
      const tree = await api.tables(accessToken);
      setSchema(tree);
    } catch {
      // schema panel will show empty state
    } finally {
      setSchemaLoading(false);
    }
  }, []);

  useEffect(() => {
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
          setAuthLoading(false);
          loadSchema(freshToken);
        }
      }
    );
    return () => subscription.unsubscribe();
  }, []);

  async function runQuery() {
    if (!sql.trim() || running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.query(token, sql) as QueryResult & { error?: string };
      if (res.error) {
        setError(res.error);
      } else {
        setResult(res);
        setViewMode("table");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  function handleTableClick(schemaName: string, table: string) {
    setSql(`SELECT *\nFROM ${schemaName}.${table}\nLIMIT 100`);
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-4xl animate-pulse">&#x1F995;</div>
      </div>
    );
  }

  const showChart = result !== null && canChart(result);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Nav email={email} />

      <div className="flex flex-1 overflow-hidden">
        {/* Schema panel */}
        <aside className="w-56 flex-shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col overflow-hidden">
          <div className="px-3 py-2.5 border-b border-zinc-800 flex-shrink-0">
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Schema</span>
          </div>
          <SchemaPanel
            schema={schema}
            loading={schemaLoading}
            onTableClick={handleTableClick}
          />
        </aside>

        {/* Main area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* SQL editor (top ~40%) */}
          <div className="flex-shrink-0 h-[42%] p-3 pb-0">
            <SqlEditor
              value={sql}
              onChange={setSql}
              onRun={runQuery}
              disabled={running}
            />
          </div>

          {/* Results (bottom ~58%) */}
          <div className="flex-1 flex flex-col overflow-hidden p-3">
            <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg flex flex-col overflow-hidden">
              {/* Result header / tabs */}
              <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800 flex-shrink-0">
                {result !== null && (
                  <>
                    <button
                      onClick={() => setViewMode("table")}
                      className={`text-xs px-2.5 py-1 rounded transition-colors ${
                        viewMode === "table"
                          ? "bg-zinc-700 text-white"
                          : "text-zinc-500 hover:text-zinc-300"
                      }`}
                    >
                      Table
                    </button>
                    {showChart && (
                      <button
                        onClick={() => setViewMode("chart")}
                        className={`text-xs px-2.5 py-1 rounded transition-colors ${
                          viewMode === "chart"
                            ? "bg-zinc-700 text-white"
                            : "text-zinc-500 hover:text-zinc-300"
                        }`}
                      >
                        Chart
                      </button>
                    )}
                  </>
                )}
                {!result && !error && !running && (
                  <span className="text-xs text-zinc-600">Run a query to see results</span>
                )}
                {running && (
                  <span className="text-xs text-zinc-500 animate-pulse">Running…</span>
                )}
              </div>

              {/* Result content */}
              <div className="flex-1 overflow-hidden">
                {error && (
                  <div className="p-4 text-red-400 text-sm font-mono whitespace-pre-wrap">{error}</div>
                )}
                {result && viewMode === "table" && <ResultTable result={result} />}
                {result && viewMode === "chart" && showChart && <QueryChart result={result} />}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
