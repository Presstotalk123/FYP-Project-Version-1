'use client';

import { useState } from 'react';
import { raService } from '@/services/ra.service';
import { RaError } from '@/types/ra.types';
import { FieldError } from './RaPartEditor';

const PLACEHOLDER = `STUDENT(*Sid, Sname, Sex, Age, Year, GPA)
DEPT(*Dname, Numphds)
ENROLL(*Sid, Grade, *Dname, *Cno, *Sectno)`;

/**
 * Write the schema as the tutorials print it, keys marked with *, and turn it into the
 * CREATE TABLE statements below it, which staff can still edit. Collapsed once there is SQL.
 */
export function RaSchemaText({ schemaSql, onConvert, disabled }: {
  schemaSql: string; onConvert: (sql: string) => void; disabled: boolean;
}) {
  const [open, setOpen] = useState(() => !schemaSql.trim());
  const [text, setText] = useState('');
  const [linkKeys, setLinkKeys] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<RaError | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const convert = async () => {
    if (schemaSql.trim() && !window.confirm('Replace the CREATE TABLE statements below with the converted schema?')) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const r = await raService.schemaFromText(text, linkKeys);
      if (r.ok) {
        onConvert(r.schema_sql);
        setMessage(`Converted ${r.relations.length} relation${r.relations.length === 1 ? '' : 's'} below. Types were `
          + 'guessed from the attribute names (Sid → INTEGER, GPA → REAL, otherwise TEXT): check them and edit anything wrong.');
      } else if (r.error) {
        setError(r.error);
      }
    } catch {
      setMessage('Could not convert: the server did not answer. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <div>
        <button type="button" className="btn btn-secondary" onClick={() => setOpen(true)} disabled={disabled}>
          Write the schema as text instead
        </button>
      </div>
    );
  }
  return (
    <div style={{ display: 'grid', gap: 6, padding: 12, borderRadius: 8, background: 'var(--surface-muted)' }}>
      <label style={{ display: 'grid', gap: 4, fontSize: 13, fontWeight: 700 }}>
        Schema as text (optional)
        <textarea className="da-input" value={text} onChange={(e) => { setText(e.target.value); setError(null); }}
          rows={5} spellCheck={false} placeholder={PLACEHOLDER}
          style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 12, resize: 'vertical', fontWeight: 400,
            borderColor: error ? 'var(--error)' : undefined }} />
      </label>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        One relation per line, as in the tutorials; mark each key attribute with <code>*</code>. A type can follow an
        attribute (<code>GPA REAL</code>); otherwise it is guessed.
      </span>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
        <input type="checkbox" checked={linkKeys} onChange={(e) => setLinkKeys(e.target.checked)} />
        Link attributes named like another relation&apos;s key to it (foreign keys, e.g. PROF.Dname → DEPT)
      </label>
      {error && <FieldError error={error} />}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-secondary" onClick={() => void convert()}
          disabled={disabled || busy || !text.trim()}>
          {busy ? 'Converting…' : 'Convert to CREATE TABLE ↓'}
        </button>
        {message && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{message}</span>}
      </div>
    </div>
  );
}
