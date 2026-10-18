'use client';

import { ReactNode, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import type { BeforeMount, OnMount } from '@monaco-editor/react';
import { RaError } from '@/types/ra.types';

const Editor = dynamic(() => import('@monaco-editor/react'), { ssr: false });

type MonacoEditor = Parameters<OnMount>[0];
type Monaco = Parameters<OnMount>[1];

/** Operators as the course slides write them; clicking inserts the symbol at the cursor. */
const PALETTE: { symbol: string; insert?: string; title: string }[] = [
  { symbol: 'σ', title: 'Selection — σ condition R   e.g. σ School = \'SCSE\' Students' },
  { symbol: 'Π', title: 'Projection — Π attributes R   e.g. Π ID, Name Students' },
  { symbol: 'ρ', title: 'Rename — ρ NewName(a, b, …) R' },
  { symbol: 'δ', title: 'Duplicate elimination — δ R' },
  { symbol: 'γ', title: 'Grouping & aggregation — γ School, AVG(GPA) → AvgGPA R' },
  { symbol: '⋈', title: 'Natural join — R ⋈ S;  theta join — R ⋈ condition S' },
  { symbol: '⟕', title: 'Left outer join — R ⟕ S  or  R ⟕ condition S' },
  { symbol: '⟖', title: 'Right outer join — R ⟖ S' },
  { symbol: '⟗', title: 'Full outer join — R ⟗ S' },
  { symbol: '×', title: 'Cartesian product — R × S' },
  { symbol: '÷', title: 'Division — R ÷ S' },
  { symbol: '∪', title: 'Union — R ∪ S (same attributes on both sides)' },
  { symbol: '∩', title: 'Intersection — R ∩ S' },
  { symbol: '−', title: 'Difference — R − S' },
  { symbol: ':=', insert: ' := ', title: 'Assignment — R1 := expression' },
  { symbol: '→', insert: ' → ', title: 'Name a new attribute — Quiz1 + Quiz2 → Total' },
  { symbol: '≠', title: 'Not equal' },
  { symbol: '≤', title: 'Less than or equal' },
  { symbol: '≥', title: 'Greater than or equal' },
  { symbol: 'AND', insert: ' AND ', title: 'Both conditions' },
  { symbol: 'OR', insert: ' OR ', title: 'Either condition' },
  { symbol: 'NOT', insert: 'NOT ', title: 'Negation' },
];

let languageRegistered = false;

/** Syntax highlighting for the course's RA notation. */
const registerRelalg: BeforeMount = (monaco) => {
  if (languageRegistered) return;
  languageRegistered = true;
  monaco.languages.register({ id: 'relalg' });
  monaco.languages.setMonarchTokensProvider('relalg', {
    tokenizer: {
      root: [
        [/(--|\/\/).*$/, 'comment'],
        [/[σπΠρδγ]|\\(select|project|rename|distinct|group)\b/, 'keyword'],
        [/[⋈⟕⟖⟗×÷∪∩−]|\\(join|leftjoin|rightjoin|fulljoin|cross|divide|union|intersect|diff)\b/, 'operator'],
        [/:=|←|→|->/, 'operator'],
        [/\b(AND|OR|NOT|and|or|not)\b|[∧∨¬]/, 'keyword'],
        [/\b(COUNT|SUM|AVG|MIN|MAX|count|sum|avg|min|max)\b/, 'type'],
        [/'([^']|'')*'|‘[^’]*’|"[^"]*"|“[^”]*”/, 'string'],
        [/\d+(\.\d+)?/, 'number'],
        [/[A-Za-z_]\w*(?=\s*(:=|←))/, 'variable'],
      ],
    },
  });
};

interface RaEditorProps {
  value: string;
  onChange: (value: string) => void;
  /** Ctrl/Cmd+Enter runs this (e.g. Run in the playground, Check in a question). */
  onRun?: () => void;
  /** Error to underline in the editor (from the last run). */
  error: RaError | null;
  /** Buttons shown above the palette — each page supplies its own. */
  toolbar?: ReactNode;
  height?: number | string;
}

export function RaEditor({ value, onChange, onRun, error, toolbar, height = 260 }: RaEditorProps) {
  const editorRef = useRef<MonacoEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  // Monaco keeps the Ctrl+Enter command it was given at mount, so it calls through a
  // ref that always holds the latest onRun.
  const onRunRef = useRef(onRun);
  useEffect(() => {
    onRunRef.current = onRun;
  }, [onRun]);

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => onRunRef.current?.());
  };

  // Underline the error position, like a compiler would.
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    const model = editor?.getModel();
    if (!editor || !monaco || !model) return;
    if (!error || !error.line) {
      monaco.editor.setModelMarkers(model, 'relalg', []);
      return;
    }
    const line = Math.min(error.line, model.getLineCount());
    const col = Math.max(error.col ?? 1, 1);
    monaco.editor.setModelMarkers(model, 'relalg', [{
      startLineNumber: line,
      startColumn: col,
      endLineNumber: line,
      endColumn: Math.max(col + 1, model.getLineMaxColumn(line)),
      message: `${error.message}${error.hint ? `\n${error.hint}` : ''}`,
      severity: monaco.MarkerSeverity.Error,
    }]);
  }, [error, value]);

  const insert = (text: string) => {
    const editor = editorRef.current;
    if (!editor) {
      onChange(value + text);
      return;
    }
    const selection = editor.getSelection();
    if (selection) {
      editor.executeEdits('ra-palette', [{ range: selection, text, forceMoveMarkers: true }]);
    }
    editor.focus();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
      {toolbar && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
          padding: '8px 12px', borderBottom: '1px solid var(--border)', background: 'var(--surface)',
        }}>
          {toolbar}
        </div>
      )}

      <div
        role="toolbar"
        aria-label="Relational algebra operators"
        style={{
          display: 'flex', flexWrap: 'wrap', gap: 4, padding: '8px 12px',
          borderBottom: '1px solid var(--border)', background: 'var(--surface-muted)',
        }}
      >
        {PALETTE.map((op) => (
          <button
            key={op.symbol}
            type="button"
            title={op.title}
            aria-label={op.title}
            onClick={() => insert(op.insert ?? `${op.symbol} `)}
            style={{
              minWidth: 32, height: 30, padding: '0 8px', borderRadius: 6, cursor: 'pointer',
              border: '1px solid var(--border-strong)', background: 'var(--surface)',
              fontSize: op.symbol.length > 2 ? 11 : 16, fontWeight: 600, color: 'var(--brand-charcoal)',
            }}
          >
            {op.symbol}
          </button>
        ))}
      </div>

      <div style={{ height }}>
        <Editor
          height="100%"
          language="relalg"
          theme="vs-dark"
          value={value}
          beforeMount={registerRelalg}
          onMount={handleMount}
          onChange={(v) => onChange(v || '')}
          options={{
            minimap: { enabled: false },
            fontSize: 15,
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
            fixedOverflowWidgets: true,
            quickSuggestions: false,
            suggestOnTriggerCharacters: false,
            wordBasedSuggestions: 'off',
            unicodeHighlight: { ambiguousCharacters: false },
          }}
        />
      </div>

      <div style={{
        padding: '8px 12px', borderTop: '1px solid var(--border)', fontSize: 12,
        color: 'var(--text-muted)', lineHeight: 1.6, background: 'var(--surface)',
      }}>
        Write as on the lecture slides, one step per line, e.g.{' '}
        <code>R1 := σ School = &apos;SCSE&apos; CrsSch</code>, then <code>Π Name R1</code>.
        The last line is the answer. σ, Π and ρ apply to the relation right after them; use brackets
        for more: <code>Π Name (R ⋈ S)</code>. Press <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>Enter</kbd> to run.
      </div>
    </div>
  );
}
