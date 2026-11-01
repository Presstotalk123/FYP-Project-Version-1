'use client';

/** A small relation table: column headings plus tuples, NULL shown explicitly. */
export function RaTable({
  columns,
  rows,
  caption,
  emptyText = 'No tuples',
  highlight,
  marked,
  markedTone = 'bad',
}: {
  columns: string[];
  rows: unknown[][];
  caption?: string;
  emptyText?: string;
  /** Optional row tint, e.g. red for tuples that shouldn't be there. */
  highlight?: 'bad' | 'good';
  /** Tint only these rows (``marked[i]`` for row i), in ``markedTone``, with a ✗ or ✓ at the end. */
  marked?: boolean[];
  markedTone?: 'bad' | 'good';
}) {
  const tone = (t: 'bad' | 'good' | undefined) => (t === 'bad' ? '#fef2f2' : t === 'good' ? '#f0fdf4' : undefined);
  const tint = tone(highlight);
  const markTint = tone(markedTone);
  const anyMarked = !!marked?.some(Boolean);
  return (
    <div style={{ display: 'grid', gap: 4 }}>
      {caption && <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--brand-charcoal)' }}>{caption}</span>}
      <div className="table-wrap">
        <table className="da-table">
          <thead>
            <tr>
              {columns.map((c, i) => <th key={`${c}-${i}`}>{c}</th>)}
              {anyMarked && <th aria-label="Marked" />}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={Math.max(columns.length + (anyMarked ? 1 : 0), 1)} style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  {emptyText}
                </td>
              </tr>
            ) : (
              rows.map((row, r) => (
                <tr key={r} style={marked?.[r] ? { background: markTint } : tint ? { background: tint } : undefined}>
                  {row.map((v, i) => (
                    <td key={i}>{v === null || v === undefined ? <span style={{ color: 'var(--text-muted)' }}>NULL</span> : String(v)}</td>
                  ))}
                  {anyMarked && (
                    <td style={{ width: 1, whiteSpace: 'nowrap', fontWeight: 700,
                      color: markedTone === 'bad' ? 'var(--error)' : 'var(--success)' }}>
                      {marked?.[r] ? (markedTone === 'bad' ? '✗ extra' : '✓ missing') : ''}
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
