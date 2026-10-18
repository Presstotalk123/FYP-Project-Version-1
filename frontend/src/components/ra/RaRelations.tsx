'use client';

import { useState } from 'react';
import { RaRelation } from '@/types/ra.types';
import { RaTable } from './RaTable';

/**
 * The schema as the slides write it — STUDENT(Sid, Sname, …) with the key underlined —
 * and, on demand, each relation's tuples.
 */
export function RaRelations({ relations }: { relations: RaRelation[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (relations.length === 0) {
    return <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>No relations loaded.</p>;
  }
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {relations.map((rel) => {
        const isOpen = open === rel.name;
        return (
          <div key={rel.name} style={{ display: 'grid', gap: 6 }}>
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : rel.name)}
              aria-expanded={isOpen}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
                padding: '6px 10px', borderRadius: 'var(--radius)', cursor: 'pointer',
                border: '1px solid var(--border)', background: 'var(--surface)',
              }}
            >
              <span style={{ fontSize: 11, color: 'var(--text-muted)', width: 10 }}>{isOpen ? '▾' : '▸'}</span>
              <code style={{ fontSize: 13, color: 'var(--brand-charcoal)', whiteSpace: 'normal' }}>
                <strong>{rel.name}</strong>(
                {rel.columns.map((c, i) => (
                  <span key={c}>
                    {i > 0 && ', '}
                    <span
                      title={rel.primary_key.includes(c) ? `${c} — part of the primary key` : `${c} (${rel.types[i]})`}
                      style={rel.primary_key.includes(c) ? { textDecoration: 'underline' } : undefined}
                    >
                      {c}
                    </span>
                  </span>
                ))}
                )
              </code>
              <span className="badge neutral" style={{ marginLeft: 'auto' }}>
                {rel.rows.length} {rel.rows.length === 1 ? 'tuple' : 'tuples'}
              </span>
            </button>
            {isOpen && (
              <div style={{ paddingLeft: 18 }}>
                <RaTable columns={rel.columns} rows={rel.rows} emptyText="No tuples (schema only)" />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
