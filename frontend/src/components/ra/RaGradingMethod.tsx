'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { RaRegradeChange, RaVerdict } from '@/types/ra.types';
import { raService } from '@/services/ra.service';
import { VERDICT_INFO } from './RaAnalyticsParts';

/**
 * Staff only: how the grader reached a verdict (backend core/ra/equivalence.py). A correct
 * verdict is either *proved* (equivalent on every valid database) or only *tested* (the
 * solver couldn't decide, so it rests on the test databases). A wrong verdict always comes
 * with a database where the answers differ.
 */
export function RaMethodTag({ verdict, method, databasesChecked }: {
  verdict: RaVerdict; method: string | null; databasesChecked?: number;
}) {
  if (verdict !== 'correct' || !method) return null;
  const proved = method === 'proof';
  return (
    <span className={`badge ${proved ? 'badge-success' : 'neutral'}`} style={{ marginLeft: 6, fontSize: 11 }}
      title={proved ? 'Proved equivalent to the model answer on every valid database'
        : 'The solver could not decide; correct on every test database'}>
      {proved ? 'proved' : `tested${databasesChecked ? ` on ${databasesChecked}` : ''}`}
    </span>
  );
}

/** Under a part's verdict bar: of the correct answers, how many were proved and how many only tested. */
export function RaCorrectBy({ counts }: { counts: { proved: number; tested: number } | undefined }) {
  if (!counts || counts.proved + counts.tested === 0) return null;
  return (
    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
      Correct answers: {counts.proved} proved equivalent on every valid database · {counts.tested} only tested
      (the solver couldn&apos;t decide)
    </span>
  );
}

function Verdict({ v, marks }: { v: RaRegradeChange['old']; marks: boolean }) {
  return (
    <span style={{ color: v.correct ? 'var(--success)' : 'var(--error)' }}>
      {VERDICT_INFO[v.verdict]?.label ?? v.verdict}
      {marks && v.marks_earned != null && ` · ${v.marks_earned} marks`}
      {v.verdict === 'correct' && v.method && <span style={{ color: 'var(--text-muted)' }}> ({v.method === 'proof' ? 'proved' : 'tested'})</span>}
    </span>
  );
}

function ChangeTable({ rows }: { rows: RaRegradeChange[] }) {
  const marks = rows.some((r) => r.old.marks_earned != null || r.new.marks_earned != null);
  return (
    <div className="table-wrap">
      <table className="da-table">
        <thead><tr><th>Student</th><th>Answer</th><th>Was</th><th>Now</th></tr></thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.attempt_id}>
              <td style={{ fontSize: 13 }}><span className="pii">{c.student || c.email}</span></td>
              <td><pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'var(--font-geist-mono)', fontSize: 12 }}>{c.answer}</pre></td>
              <td style={{ fontSize: 13 }}><Verdict v={c.old} marks={marks} /></td>
              <td style={{ fontSize: 13 }}>
                <Verdict v={c.new} marks={marks} />
                {c.overridden && <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>You overrode this one: your mark still decides.</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Regrade every past attempt at this question with the current grader. Staff first see
 * what would change; nothing is saved until they press Save. Marks set by hand are kept.
 */
export function RaRegradePanel({ questionId }: { questionId: number }) {
  const client = useQueryClient();
  const [state, setState] = useState<'idle' | 'checking' | 'checked' | 'saving' | 'saved'>('idle');
  const [progress, setProgress] = useState({ checked: 0, total: 0 });
  const [changes, setChanges] = useState<RaRegradeChange[]>([]);
  const [saved, setSaved] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const check = async () => {
    setState('checking');
    setError(null);
    setChanges([]);
    let after: number | null = null;
    const found: RaRegradeChange[] = [];
    try {
      for (;;) {
        const batch = await raService.regradePreview(questionId, after);
        found.push(...batch.changes);
        setProgress({ checked: batch.checked, total: batch.total });
        setChanges([...found]);
        if (batch.done || batch.after_id === after) break;
        after = batch.after_id;
      }
      setState('checked');
    } catch {
      setError('Could not check the attempts. Try again.');
      setState('idle');
    }
  };

  const save = async () => {
    setState('saving');
    setError(null);
    try {
      const r = await raService.regradeApply(questionId, changes.map((c) => c.attempt_id));
      setSaved(r.changed);
      setState('saved');
      await client.invalidateQueries({ queryKey: ['ra', 'analytics'] });
    } catch {
      setError('Could not save the changes. Nothing was changed.');
      setState('checked');
    }
  };

  const verdictChanges = changes.filter((c) => c.verdict_changed);
  const methodOnly = changes.filter((c) => !c.verdict_changed);

  return (
    <details className="card" style={{ padding: 16 }}>
      <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Regrade past attempts with the current grader</summary>
      <div style={{ display: 'grid', gap: 10, marginTop: 10, fontSize: 13 }}>
        <span style={{ color: 'var(--text-muted)' }}>
          The grader now proves answers equivalent on every valid database (respecting keys and foreign keys), so some
          earlier verdicts may change. This re-checks every attempt at this question and shows what would change.
          Nothing is saved until you press Save, and marks you set by hand are kept.
        </span>
        <div className="button-row">
          <button className="btn btn-secondary" onClick={check} disabled={state === 'checking' || state === 'saving'}>
            {state === 'checking' ? `Checking… ${progress.checked} of ${progress.total}` : 'Check past attempts'}
          </button>
          {state === 'checked' && changes.length > 0 && (
            <button className="btn btn-primary" onClick={save}>
              Save these {changes.length} change{changes.length === 1 ? '' : 's'}
            </button>
          )}
        </div>
        {error && <div className="alert-error">{error}</div>}
        {state === 'saved' && <div className="alert-success">Saved: {saved} attempt{saved === 1 ? '' : 's'} updated.</div>}
        {state === 'checked' && changes.length === 0 && (
          <div className="alert-info">All {progress.total} attempt{progress.total === 1 ? '' : 's'} would keep their result.</div>
        )}
        {verdictChanges.length > 0 && state !== 'saved' && (
          <div style={{ display: 'grid', gap: 6 }}>
            <strong>Verdict or marks would change ({verdictChanges.length})</strong>
            <ChangeTable rows={verdictChanges} />
          </div>
        )}
        {methodOnly.length > 0 && state !== 'saved' && (
          <details>
            <summary style={{ cursor: 'pointer' }}>
              Same verdict, decided differently ({methodOnly.length}): e.g. now proved instead of only tested
            </summary>
            <ChangeTable rows={methodOnly} />
          </details>
        )}
      </div>
    </details>
  );
}
