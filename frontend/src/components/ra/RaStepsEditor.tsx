'use client';

import { useState } from 'react';
import { raService } from '@/services/ra.service';
import { RaError, RaStepSpecStaff, RaValidateResponse } from '@/types/ra.types';
import { RaEditor } from './RaEditor';
import { RaRelations } from './RaRelations';
import { RaSteps } from './RaSteps';
import { RaSuiteReport } from './RaVerdict';
import { defaultStepName, MAX_STEPS, MIN_STEPS, stepsTotal } from './raAnswerFormat';

/**
 * A multi-step part's steps in the staff form: for each, its name (later steps use it),
 * the prompt students see above the box, its marks and its model answer (one expression).
 * The last step is the final answer and has no name. "Check the steps" validates them all
 * and builds the test databases, as "Check the model answer" does for other types.
 */
export function RaStepsEditor({ steps, onChange, schemaSql, dataSql, exampleDataSql, compareBags, names, error, busy }: {
  steps: RaStepSpecStaff[];
  onChange: (steps: RaStepSpecStaff[]) => void;
  schemaSql: string;
  dataSql: string;
  exampleDataSql: string | null;
  compareBags: boolean;
  names: string[];
  /** A save error in these steps (``step`` null: about the steps as a whole). */
  error: { step: number | null; error: RaError } | null;
  busy: boolean;
}) {
  const [validation, setValidation] = useState<RaValidateResponse | null>(null);
  const [checkError, setCheckError] = useState<{ step: number | null; error: RaError } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const last = steps.length - 1;
  const set = (index: number, change: Partial<RaStepSpecStaff>) =>
    onChange(steps.map((s, i) => (i === index ? { ...s, ...change } : s)));
  // Steps before the final one can be added, moved and removed; the final step stays last.
  const add = () => {
    const at = Math.max(0, last);
    const used = new Set(steps.map((s) => s.name?.toLowerCase()));
    let n = at;
    while (used.has(defaultStepName(n).toLowerCase())) n += 1;
    const next = [...steps];
    next.splice(at, 0, { name: defaultStepName(n), prompt: '', marks: 1, model_answer: '' });
    onChange(next);
  };
  const remove = (index: number) => onChange(steps.filter((_, i) => i !== index));
  const move = (index: number, delta: -1 | 1) => {
    const next = [...steps];
    [next[index], next[index + delta]] = [next[index + delta], next[index]];
    onChange(next);
  };

  const check = async () => {
    setWorking(true);
    setMessage(null);
    try {
      const v = await raService.validateQuestion({
        schema_sql: schemaSql, data_sql: dataSql, compare_bags: compareBags,
        example_data_sql: dataSql.trim() ? null : exampleDataSql,
        model_answer: '', checkpoints: null, answer_format: 'multi_step', steps,
      });
      setValidation(v);
      if (v.ok || !v.error) setCheckError(null);
      else if (v.error_source === 'steps' || v.error_source === 'model_answer') setCheckError({ step: v.error_step, error: v.error });
      else {
        setCheckError(null);
        setMessage(`The ${v.error_source === 'data' ? 'INSERT statements have' : 'CREATE TABLE statements have'} an error: ${v.error.message}`);
      }
    } catch {
      setMessage('Could not reach the server.');
    } finally {
      setWorking(false);
    }
  };

  const shown = error ?? checkError;
  const disabled = busy || working;
  const total = stepsTotal(steps);

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 700 }}>Steps ({steps.length})</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {total} {total === 1 ? 'mark' : 'marks'} in total. Students see each prompt with an empty box; the model answers
          are never shown. A later step can use an earlier one by its name.
        </span>
      </div>

      {steps.map((step, i) => {
        const final = i === last;
        const stepError = shown && shown.step === i ? shown.error : null;
        const earlier = steps.slice(0, i).map((s) => s.name).filter((n): n is string => !!n);
        return (
          <div key={i} style={{
            display: 'grid', gap: 8, padding: 12, borderRadius: 'var(--radius)', background: 'var(--surface)',
            border: `1px solid ${stepError ? 'var(--error)' : 'var(--border)'}`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <strong style={{ fontSize: 14, marginRight: 'auto' }}>{final ? 'Final answer (last step)' : `Step ${i + 1}`}</strong>
              {!final && (
                <>
                  <button type="button" className="btn btn-ghost" style={small} onClick={() => move(i, -1)}
                    disabled={disabled || i === 0} aria-label={`Move step ${i + 1} up`}>↑</button>
                  <button type="button" className="btn btn-ghost" style={small} onClick={() => move(i, 1)}
                    disabled={disabled || i >= last - 1} aria-label={`Move step ${i + 1} down`}>↓</button>
                  <button type="button" className="btn btn-ghost" style={small} onClick={() => remove(i)}
                    disabled={disabled || steps.length <= MIN_STEPS}>Remove</button>
                </>
              )}
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {!final && (
                <label style={{ ...label, width: 130 }}>
                  Name
                  <input className="da-input" value={step.name ?? ''} maxLength={32} placeholder={defaultStepName(i)}
                    onChange={(e) => set(i, { name: e.target.value })} />
                </label>
              )}
              <label style={{ ...label, flex: '1 1 260px' }}>
                Prompt (shown to students)
                <input className="da-input" value={step.prompt} maxLength={300}
                  placeholder={final ? 'e.g. the names of students who took every SCSE course' : 'e.g. the courses of the SCSE school'}
                  onChange={(e) => set(i, { prompt: e.target.value })} />
              </label>
              <label style={{ ...label, width: 100 }}>
                Marks
                <input className="da-input" type="number" min={0} max={100} value={step.marks}
                  onChange={(e) => set(i, { marks: Math.max(0, Math.min(100, Math.floor(Number(e.target.value) || 0))) })} />
              </label>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', minWidth: 0 }}>
              <code style={{ fontSize: 14, fontWeight: 700, paddingTop: 10, whiteSpace: 'nowrap' }}>
                {final ? '' : `${step.name?.trim() || defaultStepName(i)} :=`}
              </code>
              <div style={{ flex: 1, minWidth: 0 }}>
                <RaEditor value={step.model_answer} onChange={(v) => set(i, { model_answer: v })} error={stepError}
                  onRun={() => void check()} height={84} names={[...names, ...earlier]}
                  hint={<>Model answer for this step: one expression{earlier.length ? `; it can use ${earlier.join(', ')}` : ''}.</>} />
              </div>
            </div>
            {stepError && <StepError error={stepError} />}
          </div>
        );
      })}

      {shown && shown.step == null && <StepError error={shown.error} />}
      {message && <div className="alert-error" style={{ fontSize: 13 }}>{message}</div>}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <button type="button" className="btn btn-secondary" onClick={add} disabled={disabled || steps.length >= MAX_STEPS}>
          + Add a step
        </button>
        <button type="button" className="btn btn-brand" onClick={() => void check()}
          disabled={disabled || !schemaSql.trim() || steps.length === 0}>
          {working ? 'Checking… (building test databases)' : 'Check the steps'}
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{MIN_STEPS}–{MAX_STEPS} steps; new steps go before the final answer.</span>
      </div>

      {validation?.ok && (
        <div style={{ display: 'grid', gap: 10 }}>
          <div className="alert-success" style={{ fontSize: 13 }}>
            ✓ Every step runs. {validation.suite && <>
              The test databases catch {validation.suite.mutants_killed} of {validation.suite.mutants} deliberately wrong versions.
            </>}
          </div>
          {validation.suite && <RaSuiteReport suite={validation.suite} />}
          {validation.model_result && (
            <details>
              <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 13 }}>
                Each step&apos;s result {validation.model_result_source === 'sample' ? 'on your data'
                  : validation.model_result_source === 'example' ? 'on the example data students see'
                    : 'on an example generated database'}
              </summary>
              <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                {validation.model_result_source === 'generated' && <RaRelations relations={validation.relations} />}
                <RaSteps steps={validation.model_result.steps} />
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function StepError({ error }: { error: RaError }) {
  return (
    <div className="alert-error" style={{ fontSize: 13 }}>
      {error.line ? `Line ${error.line}${error.col ? `, column ${error.col}` : ''}: ` : ''}{error.message}
      {error.hint && <div>{error.hint}</div>}
    </div>
  );
}

const label: React.CSSProperties = { display: 'grid', gap: 4, fontSize: 13, fontWeight: 700 };
const small: React.CSSProperties = { minHeight: 28, padding: '0 10px', fontSize: 12 };
