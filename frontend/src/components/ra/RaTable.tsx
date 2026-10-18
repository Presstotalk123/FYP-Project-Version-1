'use client';

/** A small relation table: column headings plus tuples, NULL shown explicitly. */
export function RaTable({
  columns,
  rows,
  caption,
  emptyText = 'No tuples',
  highlight,
}: {
  columns: string[];
  rows: unknown[][];
  caption?: string;
  emptyText?: string;
  /** Optional row tint, e.g. red for tuples that shouldn't be there. */
  highlight?: 'bad' | 'good';
}) {
  const tint = highlight === 'bad' ? '#fef2f2' : highlight === 'good' ? '#f0fdf4' : undefined;
  return (
    <div style={{ display: 'grid', gap: 4 }}>
      {caption && <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--brand-charcoal)' }}>{caption}</span>}
      <div className="table-wrap">
        <table className="da-table">
          <thead>
            <tr>
              {columns.map((c, i) => <th key={`${c}-${i}`}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={Math.max(columns.length, 1)} style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  {emptyText}
                </td>
              </tr>
            ) : (
              rows.map((row, r) => (
                <tr key={r} style={tint ? { background: tint } : undefined}>
                  {row.map((v, i) => (
                    <td key={i}>{v === null || v === undefined ? <span style={{ color: 'var(--text-muted)' }}>NULL</span> : String(v)}</td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
