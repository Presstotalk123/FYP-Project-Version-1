'use client';

import { RaStepProgress } from '@/types/ra.types';

/**
 * Under a multi-step part in the staff analytics: "Details" opens how far students got,
 * step by step (from each student's best Submit). The analytics themselves stay one row
 * per question and part; this is only there when staff want to look.
 */
export function RaStepProgressDetails({ steps }: { steps: RaStepProgress[] }) {
  const students = steps.length ? steps[0].reached + steps[0].missed : 0;
  return (
    <details>
      <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>Details: how far students got, step by step</summary>
      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          From each student&apos;s best Submit ({students} student{students === 1 ? '' : 's'}). “Reached” includes those who
          got the step through carry-forward: wrong only because an earlier step was.
        </span>
        <div className="table-wrap">
          <table className="da-table">
            <thead>
              <tr>
                <th>Step</th><th>Prompt</th><th style={{ textAlign: 'right' }}>Marks</th>
                <th style={{ minWidth: 180 }}>Reached</th>
                <th style={{ textAlign: 'right' }}>Of them, carried forward</th>
                <th style={{ textAlign: 'right' }}>Missed</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((s, i) => {
                const share = students ? s.reached / students : 0;
                return (
                  <tr key={s.index}>
                    <td><code>{i === steps.length - 1 ? 'final' : s.name}</code></td>
                    <td style={{ fontSize: 13 }}>{s.prompt}</td>
                    <td style={{ textAlign: 'right' }}>{s.marks}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ flex: 1, height: 8, borderRadius: 4, background: 'var(--surface-muted)', overflow: 'hidden' }}>
                          <div style={{ width: `${share * 100}%`, height: '100%', background: 'var(--success)' }} />
                        </div>
                        <span style={{ fontSize: 13, minWidth: 60, textAlign: 'right' }}>
                          {s.reached} ({Math.round(share * 100)}%)
                        </span>
                      </div>
                    </td>
                    <td style={{ textAlign: 'right' }}>{s.carried}</td>
                    <td style={{ textAlign: 'right', color: s.missed ? 'var(--error)' : undefined }}>{s.missed}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  );
}
