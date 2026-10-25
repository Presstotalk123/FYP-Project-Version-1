'use client';

import { useState } from 'react';
import { DatabaseState } from '@/types/lab.types';

/* ── SVG icons ── */
const IconChevronDown = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="6 9 12 15 18 9"/>
  </svg>
);
const IconChevronRight = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="9 18 15 12 9 6"/>
  </svg>
);

interface DatabaseStateViewProps {
  databaseState: DatabaseState | null;
  isLoading: boolean;
}

/** Collapsible list of tables (schema + sample rows) — the "Database" tab in labs and SQL questions. */
export function DatabaseStateView({ databaseState, isLoading }: DatabaseStateViewProps) {
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());

  const toggleTable = (tableName: string) => {
    const newExpanded = new Set(expandedTables);
    if (newExpanded.has(tableName)) newExpanded.delete(tableName);
    else newExpanded.add(tableName);
    setExpandedTables(newExpanded);
  };

  if (isLoading) {
    return (
      <div className="loading-center" style={{ minHeight: 120 }}>
        <div className="spinner" style={{ width: 20, height: 20 }} />
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Loading database state…</span>
      </div>
    );
  }

  if (!databaseState) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13 }}>
        No database state available
      </div>
    );
  }

  if (databaseState.tables.length === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13 }}>
        No tables in database
      </div>
    );
  }

  return (
    <div style={{ padding: 12, display: 'grid', gap: 8 }}>
      {databaseState.tables.map(table => (
        <div key={table.name} className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {/* Table header - always visible */}
          <button
            style={{
              width: '100%', background: 'none', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 12px', textAlign: 'left',
            }}
            onClick={() => toggleTable(table.name)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
                {expandedTables.has(table.name) ? <IconChevronDown /> : <IconChevronRight />}
              </span>
              <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--text)' }}>{table.name}</span>
            </div>
            <span className="badge badge-info">{table.row_count} rows</span>
          </button>

          {/* Collapsed: column names */}
          {!expandedTables.has(table.name) && (
            <p style={{ margin: 0, padding: '0 12px 10px', fontSize: 11, color: 'var(--text-muted)' }}>
              {table.columns.map(col => col.name).join(', ')}
            </p>
          )}

          {/* Expanded: schema + data */}
          {expandedTables.has(table.name) && (
            <div style={{ padding: '0 12px 12px', display: 'grid', gap: 10 }}>
              <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />
              <p style={{ margin: 0, fontSize: 11, fontWeight: 700, color: 'var(--brand-charcoal)' }}>Schema:</p>
              <pre style={{
                margin: 0, fontSize: 11, lineHeight: 1.5,
                background: '#1e1e1e', color: '#d4d4d4',
                padding: '8px 10px', borderRadius: 'var(--radius)',
                overflow: 'auto', fontFamily: 'var(--font-geist-mono)',
              }}>
                {table.columns.map(col =>
                  `${col.name} ${col.type}${col.pk ? ' PRIMARY KEY' : ''}${col.notnull ? ' NOT NULL' : ''}`
                ).join('\n')}
              </pre>

              {table.sample_data.rows.length > 0 && (
                <>
                  <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />
                  <p style={{ margin: 0, fontSize: 11, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
                    Data Preview ({table.sample_data.rows.length} of {table.row_count} rows):
                  </p>
                  <div className="table-wrap" style={{ overflowX: 'auto' }}>
                    <table className="da-table da-table--data" style={{ fontSize: 11 }}>
                      <thead>
                        <tr>
                          {table.sample_data.columns.map(col => <th key={col}>{col}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {table.sample_data.rows.map((row, idx) => (
                          <tr key={idx}>
                            {table.sample_data.columns.map(col => (
                              <td key={col}>
                                {row[col] === null ? 'NULL' : typeof row[col] === 'object' ? JSON.stringify(row[col]) : String(row[col])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
