'use client';

import { RaCase } from '@/types/ra.types';
import { RaTable } from './RaTable';

/**
 * A small database where two answers differ, and what each returns on it: the
 * counterexample of a wrong answer, or the example for a "close" step.
 */
export function RaCaseView({ example, studentLabel = 'Your answer', expectedLabel = 'Model answer' }: {
  example: RaCase;
  studentLabel?: string;
  expectedLabel?: string;
}) {
  const tables = Object.entries(example.tables);
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div style={{ display: 'grid', gap: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>
          {tables.length === 0 ? 'Every relation is empty' : 'On this database'}
        </span>
        {tables.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {tables.map(([name, t]) => (
              <div key={name} style={{ minWidth: 160 }}>
                <RaTable caption={name} columns={t.columns} rows={t.rows} />
              </div>
            ))}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ minWidth: 160, flex: 1 }}>
          <RaTable caption={`${studentLabel} returns`} columns={example.student.columns}
            rows={example.student.rows} emptyText="No tuples" highlight="bad" />
        </div>
        <div style={{ minWidth: 160, flex: 1 }}>
          <RaTable caption={`${expectedLabel} returns`} columns={example.expected.columns}
            rows={example.expected.rows} emptyText="No tuples" highlight="good" />
        </div>
      </div>
    </div>
  );
}
