'use client';

import { raService } from '@/services/ra.service';
import { RaAnswerFormat, RaError, RaPartInput } from '@/types/ra.types';
import { emptySteps, RA_FORMAT_LABEL, RA_FORMATS } from './raAnswerFormat';

/**
 * The question type in the staff form: Mixed, Final answer or Multi-step, for the whole
 * question. A new question starts with none chosen, and it can't be saved until one is.
 * Once anyone has submitted an answer the type is locked (their marks were given under it).
 */
export function RaFormatPicker({ value, onChange, locked, busy, error, notes }: {
  value: RaAnswerFormat | null;
  onChange: (format: RaAnswerFormat) => void;
  locked: boolean;
  busy: boolean;
  error: RaError | null;
  /** What the last switch did to the model answers (e.g. a part to rewrite by hand). */
  notes: string[];
}) {
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div role="radiogroup" aria-label="Question type"
        style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        {RA_FORMATS.map((f) => {
          const selected = value === f.value;
          return (
            <button key={f.value} type="button" role="radio" aria-checked={selected}
              disabled={busy || (locked && !selected)} onClick={() => !selected && onChange(f.value)}
              style={{
                textAlign: 'left', padding: 12, borderRadius: 'var(--radius)', display: 'grid', gap: 4,
                cursor: busy || (locked && !selected) ? 'not-allowed' : 'pointer',
                border: selected ? '2px solid var(--brand-charcoal)' : '1px solid var(--border-strong)',
                background: selected ? 'var(--surface-muted)' : 'var(--surface)', opacity: locked && !selected ? 0.55 : 1,
              }}>
              <strong style={{ fontSize: 14 }}>{selected ? '● ' : '○ '}{f.label}</strong>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>{f.staff}</span>
            </button>
          );
        })}
      </div>
      {value == null && (
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Choose how students answer this question. Students only see the question laid out that way, never the choice.
        </span>
      )}
      {locked && (
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Students have answered this question, so its type stays {value ? RA_FORMAT_LABEL[value] : ''}. Make a new
          question to use another type.
        </span>
      )}
      {busy && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Converting the model answers…</span>}
      {notes.map((n, i) => <div key={i} className="alert-warn" style={{ fontSize: 13 }}>{n}</div>)}
      {error && <div className="alert-error" style={{ fontSize: 13 }}>{error.message}</div>}
    </div>
  );
}

function hasContent(part: RaPartInput) {
  return !!part.model_answer.trim() || !!part.steps?.some((s) => s.model_answer.trim() || s.prompt.trim());
}

/**
 * The parts rewritten for a new type (the backend joins steps into one expression, or
 * splits a model answer into steps). Parts with nothing written yet just get the new
 * type's empty shape. Returns notes for parts staff must rewrite by hand.
 */
export async function convertParts(schemaSql: string, from: RaAnswerFormat | null, to: RaAnswerFormat,
  parts: RaPartInput[], partName: (index: number) => string): Promise<{ parts: RaPartInput[]; notes: string[] }> {
  const blank = (p: RaPartInput): RaPartInput => (to === 'multi_step'
    ? { ...p, model_answer: '', checkpoints: null, steps: emptySteps(p.marks) }
    : { ...p, steps: null, checkpoints: to === 'final_answer' ? null : p.checkpoints });
  if (!parts.some(hasContent)) return { parts: parts.map(blank), notes: [] };
  if (!schemaSql.trim()) {
    throw new Error('Write the schema first: converting the model answers needs it.');
  }
  const res = await raService.convertFormat(schemaSql, from ?? 'mixed', to,
    parts.map((p) => ({ model_answer: p.model_answer, checkpoints: p.checkpoints, steps: p.steps, marks: p.marks })));
  if (!res.ok) throw new Error(`The schema has an error, so the model answers can't be converted: ${res.error?.message ?? ''}`);
  const notes: string[] = [];
  const next = parts.map((p, i) => {
    if (!hasContent(p)) return blank(p);
    const c = res.parts[i];
    if (c.error) notes.push(parts.length > 1 ? `Part ${partName(i)}: ${c.error}` : c.error);
    if (to === 'multi_step' && c.steps && c.steps.length < 2 && !c.error) {
      notes.push(`${parts.length > 1 ? `Part ${partName(i)}: ` : ''}the model answer is one expression, so it became one step (the final answer). Add the steps before it: a multi-step part needs at least 2.`);
    }
    return { ...p, model_answer: c.model_answer, checkpoints: c.checkpoints, steps: c.steps, marks: c.marks };
  });
  if (to === 'multi_step' && next.some((p) => p.steps?.some((s) => !s.prompt.trim()))) {
    notes.push('Every step needs a prompt for students: fill in the empty ones.');
  }
  return { parts: next, notes };
}
