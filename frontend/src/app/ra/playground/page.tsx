'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { SimpleGrid } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { RaEditor } from '@/components/ra/RaEditor';
import { RaOff } from '@/components/ra/RaOff';
import { RaRelations } from '@/components/ra/RaRelations';
import { RaStepStructure } from '@/components/ra/RaStepStructure';
import { RaSteps } from '@/components/ra/RaSteps';
import { RaTable } from '@/components/ra/RaTable';
import { RaSuiteReport, RaVerdict } from '@/components/ra/RaVerdict';
import { useRaStatus } from '@/hooks/use-ra-status';
import { raQueryKeys, raService } from '@/services/ra.service';
import { RaError, RaEvalResult, RaExample, RaPlaygroundGradeResponse, RaRelation } from '@/types/ra.types';

type Mode = 'run' | 'check';

/**
 * RA Playground. "Run" evaluates any expression and shows every step. "Check against a
 * model answer" grades an answer the way RA questions are graded: verdict, counterexample,
 * per-step feedback ("Show structure") and how strong the generated test data is.
 * Nothing here is saved.
 */
export default function RaPlaygroundPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Playground />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function Playground() {
  const { enabled, loading: statusLoading } = useRaStatus();
  const examplesQuery = useQuery({
    queryKey: raQueryKeys.playgroundExamples,
    queryFn: () => raService.getPlaygroundExamples(),
    enabled,
  });
  const examples = useMemo(() => examplesQuery.data ?? [], [examplesQuery.data]);

  const [mode, setMode] = useState<Mode>('run');
  const [exampleId, setExampleId] = useState('');
  const [schemaSql, setSchemaSql] = useState('');
  const [dataSql, setDataSql] = useState('');
  const [expression, setExpression] = useState('');
  const [modelAnswer, setModelAnswer] = useState('');
  const [editingSchema, setEditingSchema] = useState(false);

  const [relations, setRelations] = useState<RaRelation[]>([]);
  const [schemaError, setSchemaError] = useState<RaError | null>(null);
  const [exprError, setExprError] = useState<RaError | null>(null);
  const [modelError, setModelError] = useState<RaError | null>(null);
  const [result, setResult] = useState<RaEvalResult | null>(null);
  const [graded, setGraded] = useState<RaPlaygroundGradeResponse | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);

  const clearOutputs = () => {
    setResult(null);
    setGraded(null);
    setExprError(null);
    setModelError(null);
  };

  const fail = (err: unknown) => {
    const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    setRequestError(typeof detail === 'string' ? detail : 'Could not reach the server.');
  };

  const run = useCallback(async (schema: string, data: string, expr: string) => {
    setRunning(true);
    setRequestError(null);
    try {
      const res = await raService.runPlayground(schema, data, expr);
      setRelations(res.relations);
      setSchemaError(res.error_source === 'schema' ? res.error : null);
      setExprError(res.error_source === 'expression' ? res.error : null);
      setResult(res.result);
      setElapsedMs(expr.trim() ? res.elapsed_ms : null);
    } catch (err) {
      fail(err);
    } finally {
      setRunning(false);
    }
  }, []);

  const check = async () => {
    if (running || !expression.trim() || !modelAnswer.trim()) return;
    setRunning(true);
    setRequestError(null);
    setGraded(null);
    try {
      const res = await raService.gradePlayground(schemaSql, dataSql, modelAnswer, expression);
      setSchemaError(res.error_source === 'schema' ? res.error : null);
      setModelError(res.error_source === 'model' ? res.error : null);
      setExprError(res.grade?.verdict === 'invalid_expression' ? res.grade.error : null);
      setGraded(res);
    } catch (err) {
      fail(err);
    } finally {
      setRunning(false);
    }
  };

  const loadExample = useCallback((ex: RaExample) => {
    setExampleId(ex.id);
    setSchemaSql(ex.schema_sql);
    setDataSql(ex.data_sql);
    setExpression(ex.expressions[0] ?? '');
    setModelAnswer('');
    setResult(null);
    setGraded(null);
    setExprError(null);
    setModelError(null);
    void run(ex.schema_sql, ex.data_sql, '');
  }, [run]);

  // Start on the first example once they arrive.
  useEffect(() => {
    if (!exampleId && examples.length > 0) loadExample(examples[0]);
  }, [examples, exampleId, loadExample]);

  const currentExample = examples.find((e) => e.id === exampleId);
  const runExpression = () => {
    if (expression.trim() && !running) void run(schemaSql, dataSql, expression);
  };

  if (statusLoading) return null;
  if (!enabled) return <RaOff />;

  const gradingExamples = currentExample?.grading_examples ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Relational Algebra Playground</h2>
          <p>
            Write relational algebra as on the lecture slides. <strong>Run</strong> shows the result of every step;{' '}
            <strong>Check against a model answer</strong> grades it the way RA questions are graded. Nothing here is saved.
          </p>
        </div>
        <div className="button-row">
          <select
            className="da-select"
            aria-label="Example schema"
            value={exampleId}
            onChange={(e) => {
              const ex = examples.find((x) => x.id === e.target.value);
              if (ex) loadExample(ex);
            }}
          >
            {examples.map((ex) => <option key={ex.id} value={ex.id}>{ex.title}</option>)}
            {exampleId === 'custom' && <option value="custom">Custom schema</option>}
          </select>
        </div>
      </div>

      <div role="tablist" aria-label="Playground mode" style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['run', 'check'] as Mode[]).map((m) => (
          <button
            key={m}
            role="tab"
            aria-selected={mode === m}
            className={`btn ${mode === m ? 'btn-brand' : 'btn-secondary'}`}
            style={{ minHeight: 34, fontSize: 13 }}
            onClick={() => { setMode(m); clearOutputs(); }}
          >
            {m === 'run' ? 'Run' : 'Check against a model answer'}
          </button>
        ))}
      </div>

      {requestError && <div className="alert-error" style={{ marginBottom: 16 }}>{requestError}</div>}

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        {/* Schema */}
        <section className="card" style={{ padding: 16, display: 'grid', gap: 12, alignContent: 'start' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>Schema</h3>
            <button
              className="btn btn-secondary"
              style={{ minHeight: 28, padding: '0 10px', fontSize: 12, marginLeft: 'auto' }}
              onClick={() => setEditingSchema((v) => !v)}
            >
              {editingSchema ? 'Done editing' : 'Edit SQL'}
            </button>
          </div>
          {currentExample && !editingSchema && (
            <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>{currentExample.description}</p>
          )}

          {editingSchema && (
            <div style={{ display: 'grid', gap: 8 }}>
              <SqlBox label="CREATE TABLE statements (CHECK constraints become assumptions for generated data)"
                value={schemaSql} onChange={(v) => { setSchemaSql(v); setExampleId('custom'); }} rows={8} />
              <SqlBox label="INSERT statements (optional)" value={dataSql}
                onChange={(v) => { setDataSql(v); setExampleId('custom'); }} rows={6} />
              <div>
                <button className="btn btn-brand" style={{ minHeight: 32, fontSize: 13 }} disabled={running}
                  onClick={() => { clearOutputs(); void run(schemaSql, dataSql, ''); }}>
                  Load schema
                </button>
              </div>
            </div>
          )}

          {schemaError ? (
            <div className="alert-error" style={{ fontSize: 13 }}>{schemaError.message}</div>
          ) : (
            <RaRelations relations={relations} />
          )}

          {mode === 'run' && currentExample && currentExample.expressions.length > 1 && (
            <Suggestions title="Try one of these">
              {currentExample.expressions.map((ex) => (
                <Suggestion key={ex} onClick={() => setExpression(ex)}><code style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{ex}</code></Suggestion>
              ))}
            </Suggestions>
          )}

          {mode === 'check' && gradingExamples.length > 0 && (
            <Suggestions title="Try one of these (loads a model answer and an answer to check)">
              {gradingExamples.map((g) => (
                <Suggestion key={g.title} onClick={() => { setModelAnswer(g.model_answer); setExpression(g.answer); clearOutputs(); }}>
                  <span style={{ fontSize: 13 }}>{g.title}</span>
                </Suggestion>
              ))}
            </Suggestions>
          )}
          {mode === 'check' && gradingExamples.length === 0 && (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
              Ready-made checks are under <em>Tutorial 5.5 Q1</em> in the menu above.
            </p>
          )}
        </section>

        {/* Answer */}
        <section style={{ display: 'grid', gap: 12, alignContent: 'start', minWidth: 0 }}>
          {mode === 'check' && (
            <div style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 700 }}>Model answer</span>
              <RaEditor value={modelAnswer} onChange={setModelAnswer} error={modelError} height={130} onRun={check} />
              {modelError && <ErrorBox error={modelError} prefix="Model answer" />}
            </div>
          )}

          <div style={{ display: 'grid', gap: 6 }}>
            {mode === 'check' && <span style={{ fontSize: 13, fontWeight: 700 }}>Answer to check</span>}
            <RaEditor
              value={expression}
              onChange={setExpression}
              onRun={mode === 'run' ? runExpression : check}
              error={exprError}
              height={mode === 'run' ? 220 : 170}
              toolbar={(
                <>
                  {mode === 'run' ? (
                    <button className="btn btn-brand" style={{ minHeight: 32, padding: '0 14px', fontSize: 13 }}
                      onClick={runExpression} disabled={running || !expression.trim() || !!schemaError}>
                      {running ? 'Running…' : 'Run'}
                    </button>
                  ) : (
                    <button className="btn btn-brand" style={{ minHeight: 32, padding: '0 14px', fontSize: 13 }}
                      onClick={check} disabled={running || !expression.trim() || !modelAnswer.trim() || !!schemaError}>
                      {running ? 'Checking…' : 'Check'}
                    </button>
                  )}
                  <button className="btn btn-secondary" style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
                    onClick={() => { setExpression(''); clearOutputs(); }} disabled={running}>
                    Clear
                  </button>
                  {mode === 'run' && elapsedMs !== null && !exprError && (
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
                      Evaluated in {elapsedMs} ms
                    </span>
                  )}
                  {mode === 'check' && running && (
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
                      The first check of a model answer builds its test databases (up to a few seconds)…
                    </span>
                  )}
                </>
              )}
            />
          </div>

          {mode === 'run' && exprError && <ErrorBox error={exprError} />}

          {mode === 'run' && result && result.warnings.length > 0 && (
            <div className="alert-warn" style={{ fontSize: 13 }}>
              {result.warnings.map((w, i) => <div key={i}>{w.message}</div>)}
            </div>
          )}

          {mode === 'run' && result && (
            <div className="card" style={{ padding: 16, display: 'grid', gap: 16 }}>
              <RaTable
                caption={`Result — ${result.row_count} ${result.row_count === 1 ? 'tuple' : 'tuples'}`}
                columns={result.columns}
                rows={result.rows}
                emptyText="Empty relation"
              />
              <div style={{ display: 'grid', gap: 8 }}>
                <h3 style={{ margin: 0, fontSize: 15 }}>Steps</h3>
                <RaSteps steps={result.steps} />
              </div>
            </div>
          )}

          {mode === 'check' && graded?.grade && (
            <div className="card" style={{ padding: 16, display: 'grid', gap: 16, minWidth: 0 }}>
              <RaVerdict grade={graded.grade} />
              {graded.grade.steps.length > 0 && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <h3 style={{ margin: 0, fontSize: 15 }}>Your steps</h3>
                  <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
                    Each step is compared with the model answer&apos;s steps by what it computes, not by its name.
                    ✓ matches a model step · ◐ same kind of step but different tuples · ○ no matching step (fine for a different method).
                  </p>
                  <RaStepStructure feedback={graded.grade.steps} steps={graded.structure?.steps ?? null}
                    source={graded.structure_source} />
                </div>
              )}
              {graded.suite && <RaSuiteReport suite={graded.suite} />}
            </div>
          )}
        </section>
      </SimpleGrid>
    </>
  );
}

function ErrorBox({ error, prefix }: { error: RaError; prefix?: string }) {
  return (
    <div className="alert-error" style={{ fontSize: 13, display: 'grid', gap: 4 }}>
      <strong>
        {prefix ? `${prefix} — ` : ''}
        {error.line ? `Line ${error.line}${error.col ? `, column ${error.col}` : ''}: ` : ''}
        {error.message}
      </strong>
      {error.hint && <span>{error.hint}</span>}
    </div>
  );
}

function Suggestions({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>{title}</span>
      {children}
    </div>
  );
}

function Suggestion({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        textAlign: 'left', padding: '6px 10px', borderRadius: 'var(--radius)', cursor: 'pointer',
        border: '1px dashed var(--border-strong)', background: 'var(--surface-muted)',
      }}
    >
      {children}
    </button>
  );
}

function SqlBox({ label, value, onChange, rows }: { label: string; value: string; onChange: (v: string) => void; rows: number }) {
  return (
    <label style={{ display: 'grid', gap: 4, fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>
      {label}
      <textarea
        className="da-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        spellCheck={false}
        style={{ fontFamily: 'var(--font-geist-mono)', fontSize: 12, resize: 'vertical', fontWeight: 400, color: 'var(--text)' }}
      />
    </label>
  );
}
