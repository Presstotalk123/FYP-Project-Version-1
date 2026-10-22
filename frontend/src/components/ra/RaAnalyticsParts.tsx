'use client';

import { useQuery } from '@tanstack/react-query';
import { raQueryKeys, raService } from '@/services/ra.service';
import { RaTopError, RaVerdict, RaVerdictCounts } from '@/types/ra.types';

/** Verdicts as staff read them in analytics, with a colour each (most to least serious last). */
export const VERDICT_INFO: Record<RaVerdict, { label: string; hint: string; color: string }> = {
  correct: { label: 'Correct', hint: 'Graded correct', color: 'var(--success)' },
  wrong_in_general: {
    label: 'Wrong on some database', color: 'var(--warning)',
    hint: 'Right attributes, but a different result on at least one generated test database',
  },
  wrong_result: { label: 'Wrong on the data', hint: "A different result on the question's own data", color: 'var(--info)' },
  wrong_columns: { label: 'Wrong attributes', hint: 'The result has different attributes from the model answer', color: 'var(--brand-lilac)' },
  invalid_expression: { label: 'Has an error', hint: 'The answer could not be read or run (see the error codes)', color: 'var(--error)' },
};
const ORDER: RaVerdict[] = ['correct', 'wrong_in_general', 'wrong_result', 'wrong_columns', 'invalid_expression'];

export const percent = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`);
export const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—');

/** How the attempts split by verdict: a stacked bar and a legend with counts. */
export function VerdictBar({ verdicts, compact = false }: { verdicts: RaVerdictCounts; compact?: boolean }) {
  const total = ORDER.reduce((sum, v) => sum + (verdicts[v] ?? 0), 0);
  if (total === 0) return <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>No attempts yet</span>;
  return (
    <div style={{ display: 'grid', gap: 6, minWidth: compact ? 160 : undefined }}>
      <div role="img" aria-label={ORDER.map((v) => `${VERDICT_INFO[v].label} ${verdicts[v] ?? 0}`).join(', ')}
        style={{ display: 'flex', height: compact ? 8 : 12, borderRadius: 6, overflow: 'hidden', background: 'var(--surface-muted)' }}>
        {ORDER.filter((v) => verdicts[v]).map((v) => (
          <span key={v} title={`${VERDICT_INFO[v].label}: ${verdicts[v]}`}
            style={{ width: `${(verdicts[v] / total) * 100}%`, background: VERDICT_INFO[v].color }} />
        ))}
      </div>
      {!compact && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px', fontSize: 12 }}>
          {ORDER.map((v) => (
            <span key={v} title={VERDICT_INFO[v].hint} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 9, height: 9, borderRadius: 2, background: VERDICT_INFO[v].color }} />
              {VERDICT_INFO[v].label}: <strong>{verdicts[v] ?? 0}</strong>
              <span style={{ color: 'var(--text-muted)' }}>({percent((verdicts[v] ?? 0) / total)})</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** The commonest errors in unreadable answers. */
export function TopErrors({ errors }: { errors: RaTopError[] }) {
  if (errors.length === 0) return <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>No answers with errors.</p>;
  return (
    <div className="table-wrap">
      <table className="da-table">
        <thead><tr><th>Error</th><th>Example message</th><th style={{ textAlign: 'right' }}>Answers</th><th style={{ textAlign: 'right' }}>Students</th></tr></thead>
        <tbody>
          {errors.map((e) => (
            <tr key={e.code}>
              <td><code>{e.code}</code></td>
              <td style={{ fontSize: 13 }}>{e.example}</td>
              <td style={{ textAlign: 'right' }}>{e.count}</td>
              <td style={{ textAlign: 'right' }}>{e.students}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ClassGroupSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const groups = useQuery({ queryKey: raQueryKeys.classGroups, queryFn: () => raService.classGroups() });
  return (
    <select className="da-select" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Class group">
      <option value="">All classes</option>
      {(groups.data ?? []).map((g) => <option key={g} value={g}>{g}</option>)}
    </select>
  );
}

/** RFC-4180 CSV, downloaded with a BOM so Excel reads UTF-8 names. */
export function downloadCsv(filename: string, header: string[], rows: (string | number | null)[][]) {
  const cell = (v: string | number | null) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const text = [header, ...rows].map((r) => r.map(cell).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob(['﻿' + text], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
