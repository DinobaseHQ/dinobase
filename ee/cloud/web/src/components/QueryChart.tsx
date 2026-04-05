"use client";

import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { QueryResult } from "@/lib/api";

interface QueryChartProps {
  result: QueryResult;
}

type ChartMode = "bar" | "line" | "none";

function detectChartMode(result: QueryResult): ChartMode {
  const { columns, rows, data_types = {} } = result;
  if (!columns || !rows || columns.length < 2 || rows.length === 0) return "none";

  const valueCol = columns[1];
  const type = (data_types[valueCol] ?? "").toLowerCase();
  const isNumeric =
    type.includes("int") ||
    type.includes("float") ||
    type.includes("double") ||
    type.includes("decimal") ||
    type.includes("numeric") ||
    // fallback: check if first value parses as number
    (rows[0] !== undefined && !isNaN(Number(rows[0][valueCol])));

  if (!isNumeric) return "none";

  // If first column looks like a date → line chart
  const labelCol = columns[0];
  const labelType = (data_types[labelCol] ?? "").toLowerCase();
  const firstLabel = String(rows[0][labelCol] ?? "");
  const looksLikeDate =
    labelType.includes("date") ||
    labelType.includes("time") ||
    /^\d{4}-\d{2}/.test(firstLabel) ||
    /^\d{4}$/.test(firstLabel);

  return looksLikeDate ? "line" : "bar";
}

function buildChartData(result: QueryResult) {
  const { columns, rows } = result;
  const labelKey = columns[0];
  const valueKey = columns[1];
  return rows.map((row) => ({
    label: String(row[labelKey] ?? ""),
    value: Number(row[valueKey]) || 0,
    [labelKey]: String(row[labelKey] ?? ""),
    [valueKey]: Number(row[valueKey]) || 0,
  }));
}

export function canChart(result: QueryResult): boolean {
  return detectChartMode(result) !== "none";
}

export function QueryChart({ result }: QueryChartProps) {
  const mode = detectChartMode(result);
  if (mode === "none") {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        Chart requires 2 columns: a label and a numeric value.
      </div>
    );
  }

  const data = buildChartData(result);
  const valueKey = result.columns[1];
  const GREEN = "#22c55e";

  return (
    <div className="h-full w-full p-4">
      <ResponsiveContainer width="100%" height="100%">
        {mode === "bar" ? (
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 40, left: 16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis
              dataKey="label"
              tick={{ fill: "#a1a1aa", fontSize: 11 }}
              angle={-30}
              textAnchor="end"
              interval="preserveStartEnd"
            />
            <YAxis tick={{ fill: "#a1a1aa", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", color: "#e4e4e7" }}
              formatter={(v: number) => [v.toLocaleString(), valueKey]}
            />
            <Bar dataKey="value" fill={GREEN} radius={[3, 3, 0, 0]} />
          </BarChart>
        ) : (
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 40, left: 16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis
              dataKey="label"
              tick={{ fill: "#a1a1aa", fontSize: 11 }}
              angle={-30}
              textAnchor="end"
              interval="preserveStartEnd"
            />
            <YAxis tick={{ fill: "#a1a1aa", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", color: "#e4e4e7" }}
              formatter={(v: number) => [v.toLocaleString(), valueKey]}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={GREEN}
              strokeWidth={2}
              dot={{ fill: GREEN, r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
