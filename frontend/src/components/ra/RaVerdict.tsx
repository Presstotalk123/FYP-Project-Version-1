'use client';

import { RaGradeResult, RaSuiteSummary } from '@/types/ra.types';
import { RaCaseView } from './RaCaseView';
import { RaTable } from './RaTable';

const TITLE: Record<RaGradeResult['verdict'], { text: string; tone: 'good' | 'bad' }> = {
  correct: { text: 'Correct', tone: 'good' },
  wrong_columns: { text: 'Wrong attributes', tone: 'bad' },
  wrong_result: { text: "Wrong result on the question's data", tone: 'bad' },
  wrong_in_general: { text: 'Not correct in general', tone: 'bad' },
  invalid_expression: { text: 'The expression has an error', tone: 'bad' },
};

/** The verdict of one graded answer, with the evidence for it. */
export function RaVerdict({ grade }: { grade: RaGradeResult }) {
  const t = TITLE[grade.verdict];
  const how = grade.method === 'proof'
    ? 'Proved for every possible database'
    : grade.method === 'tested'
      ? `Checked on ${grade.databases_checked} test databases`
      : grade.method === 'sample' ? "Checked on the question's data" : null;
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className={t.tone === 'good' ? 'alert-info' : 'alert-error'} style={{ display: 'grid', gap: 4 }}>
        <strong style={{ fontSize: 15 }}>{t.tone === 'good' ? '✓' : '✗'} {t.text}</strong>
        <span style={{ fontSize: 13 }}>{grade.message}</span>
        {grade.error?.hint && <span style={{ fontSize: 13 }}>{grade.error.hint}</span>}
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {how}{how ? ' · ' : ''}{grade.elapsed_ms} ms
        </span>
      </div>

      {grade.verdict === 'wrong_columns' && (
        <div style={{ fontSize: 13 }}>
          Yours: <code>({grade.student_columns.join(', ')})</code> · asked for: <code>({grade.expected_columns.join(', ')})</code>
        </div>
      )}

      {grade.verdict === 'wrong_result' && grade.extra_rows.length > 0 && (
        <RaTable caption="Tuples your answer has that it shouldn't" columns={grade.expected_columns}
          rows={grade.extra_rows} highlight="bad" />
      )}

      {grade.counterexample && (
        <div style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>A small database where the answers differ</span>
          <RaCaseView example={grade.counterexample} />
        </div>
      )}
    </div>
  );
}

/** How strong the generated test databases are: the self-test against wrong versions. */
export function RaSuiteReport({ suite }: { suite: RaSuiteSummary }) {
  const survivors = suite.surviving_mutants;
  return (
    <details style={{ fontSize: 13 }}>
      <summary style={{ cursor: 'pointer', fontWeight: 700 }}>
        Test strength: caught {suite.mutants_killed} of {suite.mutants} deliberately wrong versions of the model answer
        ({suite.databases} test databases)
      </summary>
      <div style={{ display: 'grid', gap: 6, marginTop: 8, color: 'var(--text-muted)' }}>
        <span>
          The grader made {suite.mutants} small changes to the model answer (MIN↔MAX, &lt;↔≤, ÷ → &quot;at least one&quot;,
          ∪↔∩, a dropped condition …) and generated databases until each one gives a different result from the
          model answer on at least one of them. It tried {suite.candidates_tried} databases and kept {suite.databases}
          ({Math.round(suite.build_ms)} ms).
        </span>
        {survivors.length > 0 && (
          <>
            <span>
              Not caught, so either equivalent to the model answer (no data can tell them apart) or worth a look:
            </span>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {survivors.map((m, i) => <li key={i}><code>{m.description}</code></li>)}
            </ul>
          </>
        )}
      </div>
    </details>
  );
}
