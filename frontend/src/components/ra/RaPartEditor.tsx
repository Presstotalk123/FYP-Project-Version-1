'use client';

import { useMemo, useState } from 'react';
import { MarkdownDescriptionField } from '@/components/common/MarkdownDescriptionField';
import { raService } from '@/services/ra.service';
import {
  RaAnswerFormat, RaCheckpoint, RaError, RaPartInput, RaPartStaff, RaPlaygroundGradeResponse, RaValidateResponse,
} from '@/types/ra.types';
import { FINAL_ANSWER_HINT, hasSteps, stepsTotal } from './raAnswerFormat';
import { RaStepsEditor } from './RaStepsEditor';
import { RaStepsPreview } from './RaStepsPreview';
import { RaEditor } from './RaEditor';
import { RaRelations } from './RaRelations';
import { RaStepStructure } from './RaStepStructure';
import { RaSteps } from './RaSteps';
import { RaSuiteReport, RaVerdict } from './RaVerdict';

export type RaPartField = 'model_answer' | 'checkpoints' | 'steps';

function defaultLabel(statement: string | null) {
  return statement ? `step ${statement} of the model solution` : 'the final answer';
}

export function emptyPart(): RaPartInput {
  return { id: null, label: '', description: '', marks: 1, model_answer: '', checkpoints: null, steps: null };
}

export function partInput(p: RaPartStaff): RaPartInput {
  return {
    id: p.id, label: p.label, description: p.description, marks: p.marks,
    model_answer: p.model_answer, checkpoints: p.checkpoints, steps: p.steps,
  };
}

/** "(i)", "(ii)", … for the n-th part (0-based), as the tutorials number them. */
export function romanLabel(n: number) {
  const numerals: [number, string][] = [[10, 'x'], [9, 'ix'], [5, 'v'], [4, 'iv'], [1, 'i']];
  let rest = n + 1;
  let out = '';
  for (const [value, text] of numerals) {
    while (rest >= value) {
      out += text;
      rest -= value;
    }
  }
  return `(${out})`;
}

/**
 * One part of an RA question in the staff form: (with several parts) its label, marks and
 * text; its model answer with "Check the model answer" and the checkpoints; and a test
 * bench that grades any answer exactly as a student's would be.
 *
 * The question's type changes the middle: a Final answer part's model answer must be one
 * expression (and has no checkpoints); a Multi-step part has its steps instead
 * (RaStepsEditor), with a preview of what students see (RaStepsPreview).
 */
export function RaPartEditor({
  part, index, count, onChange, onRemove, onMove, schemaSql, dataSql, exampleDataSql, compareBags, error, busy,
  answerFormat,
}: {
  part: RaPartInput;
  index: number;
  count: number;
  onChange: (part: RaPartInput) => void;
  onRemove: () => void;
  onMove: (delta: -1 | 1) => void;
  schemaSql: string;
  dataSql: string;
  /** The example data shown to students while dataSql is empty (the model answer runs on it). */
  exampleDataSql: string | null;
  compareBags: boolean;
  error: { field: RaPartField; error: RaError; step?: number | null } | null;
  busy: boolean;
  answerFormat: RaAnswerFormat | null;
}) {
  const set = <K extends keyof RaPartInput>(key: K, value: RaPartInput[K]) => onChange({ ...part, [key]: value });
  const multi = count > 1;
  const [validation, setValidation] = useState<RaValidateResponse | null>(null);
  const [checkError, setCheckError] = useState<{ field: RaPartField; error: RaError } | null>(null);
  const [working, setWorking] = useState<'validate' | 'try' | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [tryAnswer, setTryAnswer] = useState('');
  const [tried, setTried] = useState<RaPlaygroundGradeResponse | null>(null);

  // The model answer's steps (from the last check) each become a possible checkpoint.
  const modelSteps = useMemo(
    () => (validation?.model_result?.steps ?? []).map((s, i, all) => (i === all.length - 1 ? null : s.name)),
    [validation],
  );
  const chosen = new Map((part.checkpoints ?? modelSteps.map((s) => ({ statement: s, label: defaultLabel(s) })))
    .map((c) => [c.statement ?? '', c.label]));
  const toggleCheckpoint = (statement: string | null, on: boolean, label?: string) => {
    const current: RaCheckpoint[] = modelSteps.filter((s) => chosen.has(s ?? ''))
      .map((s) => ({ statement: s, label: chosen.get(s ?? '') ?? defaultLabel(s) }));
    const others = current.filter((c) => c.statement !== statement);
    const next = on ? [...others, { statement, label: label ?? chosen.get(statement ?? '') ?? defaultLabel(statement) }] : others;
    next.sort((a, b) => modelSteps.indexOf(a.statement) - modelSteps.indexOf(b.statement));
    set('checkpoints', next);
  };

  const validate = async () => {
    setWorking('validate');
    setMessage(null);
    try {
      const v = await raService.validateQuestion({
        schema_sql: schemaSql, data_sql: dataSql, compare_bags: compareBags,
        example_data_sql: dataSql.trim() ? null : exampleDataSql,
        model_answer: part.model_answer, checkpoints: part.checkpoints,
        answer_format: answerFormat ?? 'mixed',
      });
      setValidation(v);
      if (v.ok || !v.error) {
        setCheckError(null);
      } else if (v.error_source === 'model_answer' || v.error_source === 'checkpoints') {
        setCheckError({ field: v.error_source, error: v.error });
      } else {
        setCheckError(null);
        setMessage(`The ${v.error_source === 'data' ? 'INSERT statements have' : 'CREATE TABLE statements have'} an error: ${v.error.message}`);
      }
    } catch {
      setMessage('Could not reach the server.');
    } finally {
      setWorking(null);
    }
  };

  const tryIt = async () => {
    setWorking('try');
    setMessage(null);
    try {
      setTried(await raService.gradePlayground(schemaSql, dataSql, part.model_answer, tryAnswer,
        { checkpoints: part.checkpoints, compareBags }));
    } catch {
      setMessage('Could not reach the server.');
    } finally {
      setWorking(null);
    }
  };

  const shownError = error ?? checkError;
  const errorFor = (field: RaPartField) => (shownError?.field === field ? shownError.error : null);
  const canCheck = schemaSql.trim() && part.model_answer.trim();
  const disabled = busy || !!working;
  const name = part.label.trim() || romanLabel(index);
  const stepsMode = answerFormat === 'multi_step';
  const finalOnly = answerFormat === 'final_answer';

  return (
    <div className={multi ? 'card' : undefined}
      style={{ display: 'grid', gap: 12, ...(multi ? { padding: 14, background: 'var(--surface-muted)' } : {}) }}>
      {multi && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <strong style={{ fontSize: 15, marginRight: 'auto' }}>Part {name}</strong>
            <button type="button" className="btn btn-ghost" style={smallButton} onClick={() => onMove(-1)}
              disabled={disabled || index === 0} aria-label={`Move part ${name} up`}>↑</button>
            <button type="button" className="btn btn-ghost" style={smallButton} onClick={() => onMove(1)}
              disabled={disabled || index === count - 1} aria-label={`Move part ${name} down`}>↓</button>
            <button type="button" className="btn btn-ghost" style={smallButton} onClick={onRemove} disabled={disabled}>
              Remove part
            </button>
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <label style={{ ...labelStyle, width: 140 }}>
              Label
              <input className="da-input" value={part.label} maxLength={50} placeholder={romanLabel(index)}
                onChange={(e) => set('label', e.target.value)} />
            </label>
            <label style={{ ...labelStyle, width: 140 }}>
              Marks
              {stepsMode ? (
                <input className="da-input" value={stepsTotal(part.steps)} readOnly aria-readonly
                  title="The steps' marks added up" style={{ background: 'var(--surface-muted)' }} />
              ) : (
                <input className="da-input" type="number" min={1} max={100} value={part.marks}
                  onChange={(e) => set('marks', Math.max(1, Math.min(100, Number(e.target.value) || 1)))} />
              )}
            </label>
          </div>
          <MarkdownDescriptionField id={`ra-part-${index}-description`} label={`Part ${name} (shown to students)`}
            value={part.description} onChange={(v) => set('description', v)} minHeight={70} />
        </>
      )}

      {stepsMode ? (
        <>
          <RaStepsEditor steps={part.steps ?? []} schemaSql={schemaSql} dataSql={dataSql} exampleDataSql={exampleDataSql}
            compareBags={compareBags} names={[]} busy={busy}
            error={error?.field === 'steps' ? { step: error.step ?? null, error: error.error } : null}
            onChange={(steps) => onChange({ ...part, steps, marks: Math.max(1, stepsTotal(steps)) })} />
          <RaStepsPreview steps={part.steps ?? []} schemaSql={schemaSql} dataSql={dataSql} exampleDataSql={exampleDataSql}
            compareBags={compareBags} names={[]} busy={busy} />
        </>
      ) : (
      <>
      <div style={{ display: 'grid', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{multi ? `Model answer for part ${name}` : 'Model answer'}</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {finalOnly
            ? 'Never shown to students. This is a Final answer question: write the model answer as one expression, without steps.'
            : <>Never shown to students. Write it step by step (R1 := …); its steps can be checkpoints that students&apos;
              steps are compared with.</>}
        </span>
        <RaEditor value={part.model_answer} onChange={(v) => set('model_answer', v)} error={errorFor('model_answer')}
          hint={finalOnly ? FINAL_ANSWER_HINT : undefined}
          onRun={() => void validate()} height={multi ? 140 : 180} toolbar={(
            <button type="button" className="btn btn-brand" style={{ minHeight: 32, padding: '0 14px', fontSize: 13 }}
              onClick={() => void validate()} disabled={disabled || !canCheck}>
              {working === 'validate' ? 'Checking… (building test databases)' : 'Check the model answer'}
            </button>
          )} />
        {errorFor('model_answer') && <FieldError error={errorFor('model_answer')!} />}
        {finalOnly && hasSteps(part.model_answer) && (
          <div className="alert-warn" style={{ fontSize: 13 }}>
            This is written in steps. A Final answer question needs one expression: put the steps into one
            (brackets let one expression hold everything), or switch the question to Mixed.
          </div>
        )}
        {message && <div className="alert-error" style={{ fontSize: 13 }}>{message}</div>}
      </div>

      {validation?.ok && (
        <div style={{ display: 'grid', gap: 14 }}>
          <div className="alert-success" style={{ fontSize: 13 }}>
            ✓ The model answer runs. {validation.suite && <>
              Its test databases catch {validation.suite.mutants_killed} of {validation.suite.mutants} deliberately wrong versions.
            </>}
          </div>
          {validation.suite && <RaSuiteReport suite={validation.suite} />}
          {validation.model_result && (
            <details>
              <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
                The model answer&apos;s steps {validation.model_result_source === 'sample' ? 'on your data'
                  : validation.model_result_source === 'example' ? 'on the example data students see'
                    : 'on an example generated database'}
              </summary>
              <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                {validation.model_result_source === 'generated' && <RaRelations relations={validation.relations} />}
                <RaSteps steps={validation.model_result.steps} />
              </div>
            </details>
          )}
          {modelSteps.length > 0 && !finalOnly && (
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
            </div>
          )}
        </div>
      )}
      {errorFor('checkpoints') && <FieldError error={errorFor('checkpoints')!} />}

      <details>
        <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
          Try an answer{multi ? ` to part ${name}` : ''}
        </summary>
        <div style={{ display: 'grid', gap: 10, marginTop: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Graded exactly as a student&apos;s answer would be, with the question&apos;s settings. Nothing is saved.
          </span>
          <RaEditor value={tryAnswer} onChange={setTryAnswer}
            error={tried?.grade?.verdict === 'invalid_expression' ? tried.grade.error : null}
            onRun={() => void tryIt()} height={120} toolbar={(
              <button type="button" className="btn btn-secondary" style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
                onClick={() => void tryIt()} disabled={disabled || !canCheck || !tryAnswer.trim()}>
                {working === 'try' ? 'Grading…' : 'Grade this answer'}
              </button>
            )} />
          {tried && !tried.ok && tried.error && <FieldError error={tried.error} />}
          {tried?.grade && (
            <div style={{ display: 'grid', gap: 12 }}>
              <RaVerdict grade={tried.grade} />
              <RaStepStructure feedback={tried.grade.steps} steps={tried.structure?.steps ?? null}
                source={tried.structure_source} showDirection={!finalOnly} />
            </div>
          )}
        </div>
      </details>
      </>
      )}
    </div>
  );
}

const labelStyle: React.CSSProperties = { display: 'grid', gap: 4, fontSize: 13, fontWeight: 700 };
const smallButton: React.CSSProperties = { minHeight: 28, padding: '0 10px', fontSize: 12 };

export function FieldError({ error }: { error: RaError }) {
  return (
    <div className="alert-error" style={{ fontSize: 13, fontWeight: 400 }}>
      {error.line ? `Line ${error.line}${error.col ? `, column ${error.col}` : ''}: ` : ''}{error.message}
      {error.hint && <div>{error.hint}</div>}
    </div>
  );
}
