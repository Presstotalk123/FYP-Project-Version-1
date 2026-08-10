'use client';

import { useState } from 'react';
import { DescriptionMarkdown } from './DescriptionMarkdown';

interface MarkdownDescriptionFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  minHeight?: number;
}

const labelStyle: React.CSSProperties = { fontSize: 13, fontWeight: 700, color: 'var(--brand-charcoal)' };

const toggleBtn = (active: boolean): React.CSSProperties => ({
  padding: '2px 10px',
  fontSize: 12,
  fontWeight: 650,
  cursor: 'pointer',
  border: '1px solid var(--border-strong)',
  background: active ? 'var(--brand-charcoal)' : 'var(--surface)',
  color: active ? '#fff' : 'var(--text-muted)',
});

/**
 * A Markdown-authoring description field: a monospace <textarea> with an
 * Edit/Preview toggle (previewing through DescriptionMarkdown, the same renderer
 * students see) and a Markdown hint. Mirrors the CourseInfoSettings pattern but
 * built from the plain-HTML / da-input primitives the admin forms already use,
 * so it drops into non-Mantine forms unchanged.
 *
 * Stores raw Markdown in `value` — no change to submit payloads or the backend.
 */
export function MarkdownDescriptionField({
  id,
  label,
  value,
  onChange,
  required = false,
  disabled = false,
  placeholder,
  minHeight = 100,
}: MarkdownDescriptionFieldProps) {
  const [view, setView] = useState<'edit' | 'preview'>('edit');

  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <label htmlFor={id} style={labelStyle}>
          {label} {required && <span style={{ color: 'var(--error)' }}>*</span>}
        </label>
        <div style={{ display: 'inline-flex', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
          <button
            type="button"
            style={{ ...toggleBtn(view === 'edit'), borderRadius: '4px 0 0 4px' }}
            onClick={() => setView('edit')}
          >
            Edit
          </button>
          <button
            type="button"
            style={{ ...toggleBtn(view === 'preview'), borderRadius: '0 4px 4px 0', borderLeft: 'none' }}
            onClick={() => setView('preview')}
          >
            Preview
          </button>
        </div>
      </div>

      {view === 'edit' ? (
        <textarea
          id={id}
          className="da-input"
          style={{ width: '100%', minHeight, resize: 'vertical', fontFamily: 'var(--font-geist-mono)', fontSize: 13 }}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          required={required}
        />
      ) : (
        <div
          style={{
            minHeight,
            padding: 12,
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius)',
            background: 'var(--surface-muted)',
          }}
        >
          {value.trim() ? (
            <DescriptionMarkdown content={value} />
          ) : (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Nothing to preview yet.</span>
          )}
        </div>
      )}

      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Supports Markdown (**bold**, lists, tables). Wrap ASCII tables in triple backticks (```) to keep their alignment.
      </p>
    </div>
  );
}
