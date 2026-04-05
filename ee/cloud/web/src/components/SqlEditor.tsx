"use client";

import dynamic from "next/dynamic";
import type { OnMount } from "@monaco-editor/react";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

interface SqlEditorProps {
  value: string;
  onChange: (value: string) => void;
  onRun: () => void;
  disabled?: boolean;
}

export function SqlEditor({ value, onChange, onRun, disabled }: SqlEditorProps) {
  const handleEditorMount: OnMount = (editor, monaco) => {
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
      () => { if (!disabled) onRun(); }
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 border border-zinc-800 rounded-t-lg overflow-hidden">
        <MonacoEditor
          height="100%"
          defaultLanguage="sql"
          theme="vs-dark"
          value={value}
          onChange={(v) => onChange(v ?? "")}
          onMount={handleEditorMount}
          options={{
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            lineNumbers: "on",
            renderLineHighlight: "all",
            wordWrap: "on",
            padding: { top: 12, bottom: 12 },
            suggestOnTriggerCharacters: true,
            quickSuggestions: true,
          }}
        />
      </div>
      <div className="flex items-center justify-between bg-zinc-900 border border-t-0 border-zinc-800 rounded-b-lg px-3 py-2">
        <span className="text-xs text-zinc-500">Cmd+Enter to run</span>
        <button
          onClick={onRun}
          disabled={disabled}
          className="flex items-center gap-1.5 bg-dino-green text-white text-sm font-medium px-4 py-1.5 rounded-md hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          <span>▶</span>
          <span>{disabled ? "Running…" : "Run"}</span>
        </button>
      </div>
    </div>
  );
}
