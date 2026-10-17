'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { MarkdownDescriptionField } from '@/components/common/MarkdownDescriptionField';
import { raQueryKeys, raService } from '@/services/ra.service';
import {
  RaCheckpoint, RaDifficulty, RaError, RaInputField, RaPlaygroundGradeResponse, RaQuestionInput, RaQuestionStaff,
  RaValidateResponse,
} from '@/types/ra.types';
import { RaEditor } from './RaEditor';
import { RaRelations } from './RaRelations';
import { RaStepStructure } from './RaStepStructure';
import { RaSteps } from './RaSteps';
import { RaSuiteReport, RaVerdict } from './RaVerdict';

const EMPTY: RaQuestionInput = {
  title: '', description: '', difficulty: 'medium', schema_sql: '', data_sql: '', model_answer: '',
  checkpoints: null, show_step_direction: true, compare_bags: false, hide_correctness: false, is_published: false,
};

function defaultLabel(statement: string | null) {
  return statement ? `step ${statement} of the model solution` : 'the final answer';
}

/**
 * Create or edit an RA question. "Check the model answer" validates everything and shows
 * how strong the generated test databases are before anything is saved; the test bench
 * grades any answer exactly as students' answers will be graded.
 */
export function RaQuestionForm({ initial }: { initial?: RaQuestionStaff }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<RaQuestionInput>(() => initial ? {
    title: initial.title, description: initial.description, difficulty: initial.difficulty,
    schema_sql: initial.schema_sql, data_sql: initial.data_sql, model_answer: initial.model_answer,
    checkpoints: initial.checkpoints, show_step_direction: initial.show_step_direction,
    compare_bags: initial.compare_bags, hide_correctness: initial.hide_correctness, is_published: initial.is_published,
  } : EMPTY);
  const set = <K extends keyof RaQuestionInput>(key: K, value: RaQuestionInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const [validation, setValidation] = useState<RaValidateResponse | null>(null);
  const [fieldError, setFieldError] = useState<{ field: RaInputField; error: RaError } | null>(null);
  const [busy, setBusy] = useState<'validate' | 'save' | 'try' | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [tryAnswer, setTryAnswer] = useState('');
  const [tried, setTried] = useState<RaPlaygroundGradeResponse | null>(null);

  // The model answer's steps (from the last check) each become a possible checkpoint.
  const modelSteps = useMemo(
    () => (validation?.model_result?.steps ?? []).map((s, i, all) => (i === all.length - 1 ? null : s.name)),
    [validation],
  );
  const chosen = new Map((form.checkpoints ?? modelSteps.map((s) => ({ statement: s, label: defaultLabel(s) })))
    .map((c) => [c.statement ?? '', c.label]));
  const toggleCheckpoint = (statement: string | null, on: boolean, label?: string) => {
    const current: RaCheckpoint[] = modelSteps.filter((s) => chosen.has(s ?? ''))
      .map((s) => ({ statement: s, label: chosen.get(s ?? '') ?? defaultLabel(s) }));
    const others = current.filter((c) => c.statement !== statement);
    const next = on ? [...others, { statement, label: label ?? chosen.get(statement ?? '') ?? defaultLabel(statement) }] : others;
    next.sort((a, b) => modelSteps.indexOf(a.statement) - modelSteps.indexOf(b.statement));
    set('checkpoints', next);
  };

  const content = () => ({
    schema_sql: form.schema_sql, data_sql: form.data_sql, model_answer: form.model_answer,
    checkpoints: form.checkpoints, compare_bags: form.compare_bags,
  });

  const validate = async () => {
    setBusy('validate');
    setMessage(null);
    try {
      const v = await raService.validateQuestion(content());
      setValidation(v);
      setFieldError(v.ok || !v.error_source || !v.error ? null : { field: v.error_source, error: v.error });
    } catch {
      setMessage('Could not reach the server.');
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    setBusy('save');
    setMessage(null);
    try {
      const saved = initial
        ? await raService.updateQuestion(initial.id, form)
        : await raService.createQuestion(form);
      void queryClient.invalidateQueries({ queryKey: raQueryKeys.questions });
      void queryClient.invalidateQueries({ queryKey: raQueryKeys.question(saved.id) });
      void queryClient.invalidateQueries({ queryKey: raQueryKeys.questionEdit(saved.id) });
      router.push(`/ra/questions/${saved.id}`);
    } catch (err) {
      const detail = (err as { response?: { status?: number; data?: { detail?: unknown } } }).response?.data?.detail;
      if (detail && typeof detail === 'object' && 'source' in detail) {
        const d = detail as { source: RaInputField; error: RaError };
        setFieldError({ field: d.source, error: d.error });
        setMessage('Not saved: fix the highlighted field.');
      } else if (Array.isArray(detail)) {
        setMessage('Not saved: fill in the title, description, schema and model answer.');
      } else {
        setMessage(typeof detail === 'string' ? detail : 'Not saved: could not reach the server.');
      }
      setBusy(null);
    }
  };

  const tryIt = async () => {
    setBusy('try');
    try {
      setTried(await raService.gradePlayground(form.schema_sql, form.data_sql, form.model_answer, tryAnswer,
        { checkpoints: form.checkpoints, compareBags: form.compare_bags }));
    } catch {
      setMessage('Could not reach the server.');
    } finally {
      setBusy(null);
    }
  };

  const errorFor = (field: RaInputField) => (fieldError?.field === field ? fieldError.error : null);
  const canCheck = form.schema_sql.trim() && form.model_answer.trim();

  return (
    <div style={{ display: 'grid', gap: 18, maxWidth: 1100 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <h2>{initial ? 'Edit RA question' : 'New RA question'}</h2>
          <p>Students answer in relational algebra; their answer is graded on what it computes, against your model answer.</p>
        </div>
      </div>

      <section className="card" style={{ padding: 16, display: 'grid', gap: 12 }}>
        <label style={labelStyle}>
          Title
          <input className="da-input" value={form.title} onChange={(e) => set('title', e.target.value)} maxLength={255} />
        </label>
        <label style={{ ...labelStyle, maxWidth: 220 }}>
          Difficulty
          <select className="da-select" value={form.difficulty} onChange={(e) => set('difficulty', e.target.value as RaDifficulty)}>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </label>
        <MarkdownDescriptionField id="ra-description" label="Question (shown to students)" value={form.description}
          onChange={(v) => set('description', v)} required minHeight={120} />
      </section>

      <section className="card" style={{ padding: 16, display: 'grid', gap: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Schema and data</h3>
        <SqlArea label="CREATE TABLE statements" value={form.schema_sql} onChange={(v) => set('schema_sql', v)} rows={8}
          hint="Mark keys with PRIMARY KEY and links with REFERENCES. Add a CHECK constraint for any assumption the question makes (e.g. CHECK (a < b)): generated test data will respect it."
          error={errorFor('schema')} />
        <SqlArea label="INSERT statements (optional)" value={form.data_sql} onChange={(v) => set('data_sql', v)} rows={5}
          hint="Students see this data. Leave it empty for a schema-only question, as in the tutorials: answers are then checked on generated databases only."
          error={errorFor('data')} />
      </section>

      <section className="card" style={{ padding: 16, display: 'grid', gap: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Model answer</h3>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
          Never shown to students. Write it step by step (R1 := …); its steps can be checkpoints that students&apos;
          steps are compared with.
        </p>
        <RaEditor value={form.model_answer} onChange={(v) => set('model_answer', v)} error={errorFor('model_answer')}
          onRun={() => void validate()} height={180} toolbar={(
            <button className="btn btn-brand" style={{ minHeight: 32, padding: '0 14px', fontSize: 13 }}
              onClick={() => void validate()} disabled={!!busy || !canCheck}>
              {busy === 'validate' ? 'Checking… (building test databases)' : 'Check the model answer'}
            </button>
          )} />
        {errorFor('model_answer') && <FieldError error={errorFor('model_answer')!} />}

        {validation?.ok && (
          <div style={{ display: 'grid', gap: 14 }}>
            <div className="alert-info" style={{ fontSize: 13 }}>
              ✓ The model answer runs. {validation.suite && <>
                Its test databases catch {validation.suite.mutants_killed} of {validation.suite.mutants} deliberately wrong versions.
              </>}
            </div>
            {validation.suite && <RaSuiteReport suite={validation.suite} />}
            {validation.model_result && (
              <details>
                <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
                  The model answer&apos;s steps {validation.model_result_source === 'sample'
                    ? 'on your data' : 'on an example generated database'}
                </summary>
                <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                  {validation.model_result_source === 'generated' && <RaRelations relations={validation.relations} />}
                  <RaSteps steps={validation.model_result.steps} />
                </div>
              </details>
            )}
            {modelSteps.length > 0 && (
              <div style={{ display: 'grid', gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>Checkpoints</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Students&apos; steps are compared with these steps (by content, whatever they are called). The label is
                  what students see, so describe the step without giving it away, e.g. “the Civil Engineering courses”.
                </span>
                {modelSteps.map((s) => (
                  <div key={s ?? '(final)'} style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, minWidth: 140 }}>
                      <input type="checkbox" checked={chosen.has(s ?? '')} onChange={(e) => toggleCheckpoint(s, e.target.checked)} />
                      <code>{s ?? 'final answer'}</code>
                    </label>
                    <input className="da-input" style={{ flex: '1 1 260px' }} disabled={!chosen.has(s ?? '')}
                      value={chosen.get(s ?? '') ?? defaultLabel(s)} maxLength={200}
                      aria-label={`Label shown to students for ${s ?? 'the final answer'}`}
                      onChange={(e) => toggleCheckpoint(s, true, e.target.value)} />
                  </div>
                ))}
                {errorFor('checkpoints') && <FieldError error={errorFor('checkpoints')!} />}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="card" style={{ padding: 16, display: 'grid', gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Feedback and visibility</h3>
        <Toggle checked={form.show_step_direction} onChange={(v) => set('show_step_direction', v)}
          label="Show students how each of their steps compares with the model's (✓ / ◐ / ○)" />
        <Toggle checked={form.hide_correctness} onChange={(v) => set('hide_correctness', v)}
          label="Hide correctness: students only see “Submitted”" />
        <Toggle checked={form.compare_bags} onChange={(v) => set('compare_bags', v)}
          label="Compare results as bags (duplicate tuples count; by default they don't)" />
        <Toggle checked={form.is_published} onChange={(v) => set('is_published', v)}
          label="Published (students can see it)" />
      </section>

      <section className="card" style={{ padding: 16, display: 'grid', gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Try an answer</h3>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
          Graded exactly as a student&apos;s answer would be, with the settings above. Nothing is saved.
        </p>
        <RaEditor value={tryAnswer} onChange={setTryAnswer} error={tried?.grade?.verdict === 'invalid_expression' ? tried.grade.error : null}
          onRun={() => void tryIt()} height={140} toolbar={(
            <button className="btn btn-secondary" style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
              onClick={() => void tryIt()} disabled={!!busy || !canCheck || !tryAnswer.trim()}>
              {busy === 'try' ? 'Grading…' : 'Grade this answer'}
            </button>
          )} />
        {tried && !tried.ok && tried.error && <FieldError error={tried.error} />}
        {tried?.grade && (
          <div style={{ display: 'grid', gap: 12 }}>
            <RaVerdict grade={tried.grade} />
            <RaStepStructure feedback={tried.grade.steps} steps={tried.structure?.steps ?? null}
              source={tried.structure_source} showDirection />
          </div>
        )}
      </section>

      <div className="button-row">
        <button className="btn btn-brand" onClick={() => void save()} disabled={!!busy}>
          {busy === 'save' ? 'Saving… (building test databases)' : initial ? 'Save changes' : 'Create question'}
        </button>
        <button className="btn btn-secondary" onClick={() => router.back()} disabled={!!busy}>Cancel</button>
        {message && <span style={{ fontSize: 13, color: 'var(--error)' }}>{message}</span>}
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = { display: 'grid', gap: 4, fontSize: 13, fontWeight: 700 };

function SqlArea({ label, value, onChange, rows, hint, error }: {
  label: string; value: string; onChange: (v: string) => void; rows: number; hint: string; error: RaError | null;
}) {
  return (
    <label style={labelStyle}>
      {label}
      <textarea className="da-input" value={value} onChange={(e) => onChange(e.target.value)} rows={rows} spellCheck={false}
        style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 12, resize: 'vertical', fontWeight: 400,
          borderColor: error ? 'var(--error)' : undefined }} />
      <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-muted)' }}>{hint}</span>
      {error && <FieldError error={error} />}
    </label>
  );
}

function FieldError({ error }: { error: RaError }) {
  return (
    <div className="alert-error" style={{ fontSize: 13, fontWeight: 400 }}>
      {error.line ? `Line ${error.line}${error.col ? `, column ${error.col}` : ''}: ` : ''}{error.message}
      {error.hint && <div>{error.hint}</div>}
    </div>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
