"use client";

import type { QueryResult } from "@/lib/api";

interface ResultTableProps {
  result: QueryResult;
}

export function ResultTable({ result }: ResultTableProps) {
  const { columns, rows, data_types = {}, row_count } = result;

  function typeLabel(col: string): string {
    const t = (data_types[col] ?? "").toLowerCase();
    if (t.includes("int") || t.includes("float") || t.includes("double") || t.includes("decimal") || t.includes("numeric")) return "num";
    if (t.includes("bool")) return "bool";
    if (t.includes("date") || t.includes("time") || t.includes("timestamp")) return "date";
    if (t.includes("json") || t.includes("struct") || t.includes("map") || t.includes("list")) return "json";
    return "str";
  }

  function typeBadgeClass(col: string): string {
    const label = typeLabel(col);
    if (label === "num") return "bg-blue-900/50 text-blue-400";
    if (label === "date") return "bg-purple-900/50 text-purple-400";
    if (label === "bool") return "bg-yellow-900/50 text-yellow-400";
    if (label === "json") return "bg-orange-900/50 text-orange-400";
    return "bg-zinc-800 text-zinc-400";
  }

  function formatCell(value: unknown): string {
    if (value === null || value === undefined) return "";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-xs text-zinc-500 border-b border-zinc-800 flex-shrink-0">
        {row_count} row{row_count !== 1 ? "s" : ""}
        {row_count === 500 && (
          <span className="ml-2 text-yellow-500">(result capped at 500 — add a LIMIT to see fewer)</span>
        )}
      </div>
      <div className="overflow-auto flex-1">
        <table className="w-full text-sm border-collapse">
          <thead className="sticky top-0 bg-zinc-900">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="text-left px-3 py-2 text-zinc-300 font-medium border-b border-zinc-800 whitespace-nowrap"
                >
                  <div className="flex items-center gap-1.5">
                    <span>{col}</span>
                    <span className={`text-[10px] px-1 rounded font-normal ${typeBadgeClass(col)}`}>
                      {typeLabel(col)}
                    </span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr
                key={ri}
                className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors"
              >
                {columns.map((col, ci) => {
                  const cell = row[col];
                  return (
                    <td
                      key={ci}
                      className="px-3 py-1.5 text-zinc-300 whitespace-nowrap max-w-xs truncate font-mono text-xs"
                      title={formatCell(cell)}
                    >
                      {cell === null || cell === undefined ? (
                        <span className="text-zinc-600 italic">null</span>
                      ) : (
                        formatCell(cell)
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="text-center py-10 text-zinc-600">No rows returned.</div>
        )}
      </div>
    </div>
  );
}
