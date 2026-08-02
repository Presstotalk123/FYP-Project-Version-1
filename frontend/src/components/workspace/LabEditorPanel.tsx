'use client';

import { Box } from '@mantine/core';
import dynamic from 'next/dynamic';

const Editor = dynamic(() => import('@monaco-editor/react'), { ssr: false });

/* ── SVG icons ── */
const IconPlay = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="5 3 19 12 5 21 5 3"/>
  </svg>
);
const IconTrash = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
    <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
  </svg>
);

interface LabEditorPanelProps {
  query: string;
  onQueryChange: (query: string) => void;
  onExecute: () => void;
  onClear: () => void;
  isExecuting: boolean;
  executionTime: number | null;
  labType?: 'sql' | 'graph';
  isCoolingDown?: boolean;
}

export function LabEditorPanel({
  query,
  onQueryChange,
  onExecute,
  onClear,
  isExecuting,
  executionTime,
  labType = 'sql',
  isCoolingDown = false,
}: LabEditorPanelProps) {
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 12px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
        background: 'var(--surface)',
      }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-brand"
            style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
            onClick={onExecute}
            disabled={isExecuting || isCoolingDown}
          >
            <IconPlay />
            {isExecuting ? 'Running…' : 'Run Query'}
          </button>
          <button
            className="btn btn-secondary"
            style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
            onClick={onClear}
          >
            <IconTrash />
            Clear
          </button>
          {isCoolingDown && (
            <span style={{ fontSize: 13, color: 'var(--text-muted, #888)', alignSelf: 'center' }}>
              Please wait before running another query
            </span>
          )}
        </div>
        {executionTime !== null && (
          <span className="badge neutral">{executionTime.toFixed(2)}ms</span>
        )}
      </div>

      {/* Editor */}
      <Box style={{ flex: 1, overflow: 'hidden' }}>
        <Editor
          height="100%"
          language={labType === 'graph' ? 'cypher' : 'sql'}
          theme="vs-dark"
          value={query}
          onChange={(value) => onQueryChange(value || '')}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
          }}
        />
      </Box>
    </div>
  );
}
