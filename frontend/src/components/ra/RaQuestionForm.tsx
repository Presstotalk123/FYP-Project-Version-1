'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { MarkdownDescriptionField } from '@/components/common/MarkdownDescriptionField';
import { raQueryKeys, raService } from '@/services/ra.service';
import {
  RaAnswerFormat, RaDifficulty, RaError, RaInputField, RaPartInput, RaQuestionInput, RaQuestionStaff,
} from '@/types/ra.types';
import { emptyPart, FieldError, partInput, RaPartEditor, RaPartField, romanLabel } from './RaPartEditor';
import { RaSchemaText } from './RaSchemaText';
import { RaExampleDataPanel, useRaExampleData } from './RaExampleData';
import { convertParts, RaFormatPicker } from './RaFormatPicker';
import { emptySteps, stepsProgram } from './raAnswerFormat';

const EMPTY: RaQuestionInput = {
  title: '', description: '', difficulty: 'medium', schema_sql: '', data_sql: '', example_data_sql: null, parts: [emptyPart()],
  answer_format: null, show_step_direction: true, assessment_step_direction: false, compare_bags: false,
  hide_correctness: false, is_published: false,
};

/** A field the server rejected; ``part`` is the part's index for a model answer, checkpoints
 *  or steps, ``step`` the step's index in a multi-step part. */
type SaveError = { field: RaInputField; error: RaError; part: number | null; step: number | null };

/**
 * Create or edit an RA question: one schema (and optional data) with one or more parts,
 * (i), (ii), …, each with its own model answer. "Check the model answer" validates a part
 * and shows how strong its generated test databases are before anything is saved; each
 * part's test bench grades any answer exactly as students' answers will be graded.
 */
export function RaQuestionForm({ initial }: { initial?: RaQuestionStaff }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<RaQuestionInput>(() => initial ? {
    title: initial.title, description: initial.description, difficulty: initial.difficulty,
    schema_sql: initial.schema_sql, data_sql: initial.data_sql, example_data_sql: initial.example_data_sql,
    parts: initial.parts.length ? initial.parts.map(partInput) : [emptyPart()],
    answer_format: initial.answer_format, show_step_direction: initial.show_step_direction, assessment_step_direction: initial.assessment_step_direction,
    compare_bags: initial.compare_bags, hide_correctness: initial.hide_correctness, is_published: initial.is_published,
  } : EMPTY);
  const set = <K extends keyof RaQuestionInput>(key: K, value: RaQuestionInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  // Stable keys for the part editors (their check results stay with them when parts move).
  const [keys, setKeys] = useState<number[]>(() => form.parts.map((_, i) => i));
  const [nextKey, setNextKey] = useState(form.parts.length);

  // With the INSERT box empty, students see example data instead (RaExampleData.tsx).
  const noData = !form.data_sql.trim();
  const example = useRaExampleData(form.schema_sql,
    form.parts.map((p) => (form.answer_format === 'multi_step' && p.steps ? stepsProgram(p.steps) : p.model_answer)),
    form.example_data_sql, noData, (sql) => set('example_data_sql', sql));

  const [saveError, setSaveError] = useState<SaveError | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const setPart = (index: number, part: RaPartInput) =>
    setForm((f) => ({ ...f, parts: f.parts.map((p, i) => (i === index ? part : p)) }));

  // The question type: switching rewrites every part's model answer for the new type.
  const [switching, setSwitching] = useState(false);
  const [formatNotes, setFormatNotes] = useState<string[]>([]);
  const [formatError, setFormatError] = useState<RaError | null>(null);
  const chooseFormat = async (to: RaAnswerFormat) => {
    setSwitching(true);
    setFormatError(null);
    setFormatNotes([]);
    try {
      const { parts, notes } = await convertParts(form.schema_sql, form.answer_format, to, form.parts,
        (i) => form.parts[i]?.label.trim() || romanLabel(i));
      setForm((f) => ({ ...f, answer_format: to, parts }));
      setFormatNotes(notes);
      setSaveError(null);
    } catch (err) {
      setFormatError({ code: 'RA012', message: err instanceof Error ? err.message : 'Could not convert the model answers.',
        line: null, col: null, hint: null });
    } finally {
      setSwitching(false);
    }
  };

  const addPart = () => {
    setForm((f) => {
      // Going from one part to several: label the first part too.
      const parts = f.parts.length === 1 && !f.parts[0].label.trim()
        ? [{ ...f.parts[0], label: romanLabel(0) }] : f.parts;
      const fresh = f.answer_format === 'multi_step' ? { ...emptyPart(), marks: 2, steps: emptySteps(2) } : emptyPart();
      return { ...f, parts: [...parts, { ...fresh, label: romanLabel(parts.length) }] };
    });
    setKeys((k) => [...k, nextKey]);
    setNextKey((n) => n + 1);
    setSaveError(null);
  };
  const removePart = (index: number) => {
    const part = form.parts[index];
    if (part.id != null && !window.confirm('Remove this part? Students’ answers to it will no longer count.')) return;
    setForm((f) => ({ ...f, parts: f.parts.filter((_, i) => i !== index) }));
    setKeys((k) => k.filter((_, i) => i !== index));
    setSaveError(null);
  };
  const movePart = (index: number, delta: -1 | 1) => {
    const swap = <T,>(list: T[]) => {
      const next = [...list];
      [next[index], next[index + delta]] = [next[index + delta], next[index]];
      return next;
    };
    setForm((f) => ({ ...f, parts: swap(f.parts) }));
    setKeys(swap);
    setSaveError(null);
  };

  const save = async () => {
    if (!form.answer_format) {
      setMessage('Not saved: choose the question type first.');
      return;
    }
    setBusy(true);
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
      const response = (err as { response?: { status?: number; data?: { detail?: unknown } } }).response;
      const detail = response?.data?.detail;
      if (detail && typeof detail === 'object' && 'source' in detail) {
        const d = detail as { source: RaInputField; error: RaError; part: number | null; step?: number | null };
        setSaveError({ field: d.source, error: d.error, part: d.part ?? null, step: d.step ?? null });
        const where = [
          d.part != null && form.parts.length > 1 ? `part ${form.parts[d.part]?.label.trim() || romanLabel(d.part)}` : null,
          d.step != null ? `step ${d.step + 1}` : null,
        ].filter(Boolean).join(', ');
        setMessage(d.source === 'answer_format' ? `Not saved: ${d.error.message}`
          : where ? `Not saved: fix ${where}.` : 'Not saved: fix the highlighted field.');
      } else if (Array.isArray(detail)) {
        setMessage('Not saved: fill in the title, the question, the schema and every part’s model answer.');
      } else if (typeof detail === 'string') {
        setMessage(detail);
      } else if (response) {
        setMessage(`Not saved: the server returned an error (${response.status ?? 'unknown'}). Please try again.`);
      } else {
        setMessage('Not saved: could not reach the server.');
      }
      setBusy(false);
    }
  };

  const errorFor = (field: RaInputField) => (saveError?.field === field ? saveError.error : null);
  const partError = (index: number): { field: RaPartField; error: RaError; step: number | null } | null =>
    saveError && saveError.part === index
      && (saveError.field === 'model_answer' || saveError.field === 'checkpoints' || saveError.field === 'steps')
      ? { field: saveError.field, error: saveError.error, step: saveError.step } : null;
  const multi = form.parts.length > 1;
  const totalMarks = form.parts.reduce((sum, p) => sum + (p.marks || 0), 0);

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
        <MarkdownDescriptionField id="ra-description"
          label={multi ? 'Question (shown to students above every part)' : 'Question (shown to students)'}
          value={form.description} onChange={(v) => set('description', v)} required minHeight={120} />
      </section>

      <section className="card" style={{ padding: 16, display: 'grid', gap: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Schema and data</h3>
        <RaSchemaText schemaSql={form.schema_sql} onConvert={(sql) => set('schema_sql', sql)} disabled={busy} />
        <SqlArea label="CREATE TABLE statements" value={form.schema_sql} onChange={(v) => set('schema_sql', v)} rows={8}
          hint="Mark keys with PRIMARY KEY and links with REFERENCES. Add a CHECK constraint for any assumption the question makes (e.g. CHECK (a < b)): generated test data will respect it."
          error={errorFor('schema')} />
        <SqlArea label="INSERT statements (optional)" value={form.data_sql} onChange={(v) => set('data_sql', v)} rows={5}
          hint="Students see this data. Leave it empty for a schema-only question, as in the tutorials: students then see example data made up for it (below), and answers are graded on generated databases."
          error={errorFor('data')} />
        {noData && (
          <RaExampleDataPanel preview={example.preview} error={example.error} loading={example.loading}
            chosen={form.example_data_sql != null} onRegenerate={() => void example.regenerate()} disabled={busy}
            onCopy={(sql) => setForm((f) => ({ ...f, data_sql: sql, example_data_sql: null }))} />
        )}
      </section>

      <section className="card" style={{ padding: 16, display: 'grid', gap: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Question type</h3>
        <RaFormatPicker value={form.answer_format} onChange={(f) => void chooseFormat(f)}
          locked={!!initial?.has_attempts} busy={busy || switching} notes={formatNotes}
          error={formatError ?? errorFor('answer_format')} />
      </section>

      {form.answer_format && (
      <section className="card" style={{ padding: 16, display: 'grid', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0, fontSize: 16 }}>{multi ? `Parts (${form.parts.length})` : 'Answer'}</h3>
          {multi && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {totalMarks} marks in total. Students answer each part separately on the same schema; in an assessment
              each part earns its own marks.
            </span>
          )}
        </div>
        {form.parts.map((part, index) => (
          <RaPartEditor key={keys[index]} part={part} index={index} count={form.parts.length}
            onChange={(p) => setPart(index, p)} onRemove={() => removePart(index)} onMove={(d) => movePart(index, d)}
            schemaSql={form.schema_sql} dataSql={form.data_sql} exampleDataSql={example.preview?.sql ?? null}
            compareBags={form.compare_bags} answerFormat={form.answer_format}
            error={partError(index)} busy={busy || switching} />
        ))}
        <div>
          <button type="button" className="btn btn-secondary" onClick={addPart} disabled={busy || form.parts.length >= 20}>
            + Add {multi ? 'another part' : 'a sub-question'}
          </button>
          {!multi && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 10 }}>
              e.g. parts (i)–(iv) on this schema, each with its own model answer and marks.
            </span>
          )}
        </div>
      </section>
      )}

      <section className="card" style={{ padding: 16, display: 'grid', gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Feedback and visibility</h3>
        <Toggle checked={form.show_step_direction} onChange={(v) => set('show_step_direction', v)}
          label={form.answer_format === 'final_answer'
            ? "Show students how each of their steps compares with the model's (✓ / ◐ / ○) — not used by Final answer questions, which have no steps"
            : "Show students how each of their steps compares with the model's (✓ / ◐ / ○)"} />
        <Toggle checked={form.assessment_step_direction} onChange={(v) => set('assessment_step_direction', v)}
          label="…also when this question is in an assessment (off by default: it is a strong hint)" />
        <Toggle checked={form.hide_correctness} onChange={(v) => set('hide_correctness', v)}
          label="Hide correctness: students only see “Submitted”" />
        <Toggle checked={form.compare_bags} onChange={(v) => set('compare_bags', v)}
          label="Compare results as bags (duplicate tuples count; by default they don't)" />
        <Toggle checked={form.is_published} onChange={(v) => set('is_published', v)}
          label="Published (students can see it)" />
      </section>

      <div className="button-row">
        <button className="btn btn-brand" onClick={() => void save()} disabled={busy || switching || !form.answer_format}
          title={form.answer_format ? undefined : 'Choose the question type first'}>
          {busy ? 'Saving… (building test databases)' : initial ? 'Save changes' : 'Create question'}
        </button>
        <button className="btn btn-secondary" onClick={() => router.back()} disabled={busy}>Cancel</button>
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

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
