'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { SimpleGrid } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { RaEditor } from '@/components/ra/RaEditor';
import { RaRelations } from '@/components/ra/RaRelations';
import { RaSteps } from '@/components/ra/RaSteps';
import { RaTable } from '@/components/ra/RaTable';
import { useRaStatus } from '@/hooks/use-ra-status';
import { raQueryKeys, raService } from '@/services/ra.service';
import { RaError, RaEvalResult, RaExample, RaRelation } from '@/types/ra.types';

/**
 * RA Playground: run any relational-algebra expression on a small schema and see every
 * step. Nothing is graded or saved — it's the place to try the notation and the engine.
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

  const [exampleId, setExampleId] = useState('');
  const [schemaSql, setSchemaSql] = useState('');
  const [dataSql, setDataSql] = useState('');
  const [expression, setExpression] = useState('');
  const [editingSchema, setEditingSchema] = useState(false);

  const [relations, setRelations] = useState<RaRelation[]>([]);
  const [schemaError, setSchemaError] = useState<RaError | null>(null);
  const [exprError, setExprError] = useState<RaError | null>(null);
  const [result, setResult] = useState<RaEvalResult | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);

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
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      setRequestError(typeof detail === 'string' ? detail : 'Could not reach the server.');
    } finally {
      setRunning(false);
    }
  }, []);

  const loadExample = useCallback((ex: RaExample) => {
    setExampleId(ex.id);
    setSchemaSql(ex.schema_sql);
    setDataSql(ex.data_sql);
    setExpression(ex.expressions[0] ?? '');
    setResult(null);
    setExprError(null);
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
  if (!enabled) {
    return (
      <div className="card" style={{ padding: 24, maxWidth: 640 }}>
        <h2 style={{ marginTop: 0 }}>Relational Algebra is switched off</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 0 }}>
          Set <code>RA_ENABLED=true</code> in <code>backend/.env</code> and restart the backend.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Relational Algebra Playground</h2>
          <p>Write relational algebra as on the lecture slides and see the result of every step. Nothing here is graded or saved.</p>
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
              <SqlBox label="CREATE TABLE statements" value={schemaSql} onChange={(v) => { setSchemaSql(v); setExampleId('custom'); }} rows={8} />
              <SqlBox label="INSERT statements (optional)" value={dataSql} onChange={(v) => { setDataSql(v); setExampleId('custom'); }} rows={6} />
              <div>
                <button className="btn btn-brand" style={{ minHeight: 32, fontSize: 13 }} disabled={running} onClick={() => run(schemaSql, dataSql, '')}>
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

          {currentExample && currentExample.expressions.length > 1 && (
            <div style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>Try one of these</span>
              {currentExample.expressions.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => setExpression(ex)}
                  style={{
                    textAlign: 'left', padding: '6px 10px', borderRadius: 'var(--radius)', cursor: 'pointer',
                    border: '1px dashed var(--border-strong)', background: 'var(--surface-muted)',
                  }}
                >
                  <code style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{ex}</code>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Expression */}
        <section style={{ display: 'grid', gap: 12, alignContent: 'start' }}>
          <RaEditor
            value={expression}
            onChange={setExpression}
            onRun={runExpression}
            error={exprError}
            height={220}
            toolbar={(
              <>
                <button
                  className="btn btn-brand"
                  style={{ minHeight: 32, padding: '0 14px', fontSize: 13 }}
                  onClick={runExpression}
                  disabled={running || !expression.trim() || !!schemaError}
                >
                  {running ? 'Running…' : 'Run'}
                </button>
                <button
                  className="btn btn-secondary"
                  style={{ minHeight: 32, padding: '0 12px', fontSize: 13 }}
                  onClick={() => { setExpression(''); setResult(null); setExprError(null); }}
                  disabled={running}
                >
                  Clear
                </button>
                {elapsedMs !== null && !exprError && (
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
                    Evaluated in {elapsedMs} ms
                  </span>
                )}
              </>
            )}
          />

          {exprError && (
            <div className="alert-error" style={{ fontSize: 13, display: 'grid', gap: 4 }}>
              <strong>
                {exprError.line ? `Line ${exprError.line}${exprError.col ? `, column ${exprError.col}` : ''}: ` : ''}
                {exprError.message}
              </strong>
              {exprError.hint && <span>{exprError.hint}</span>}
            </div>
          )}

          {result && result.warnings.length > 0 && (
            <div className="alert-warn" style={{ fontSize: 13 }}>
              {result.warnings.map((w, i) => <div key={i}>{w.message}</div>)}
            </div>
          )}

          {result && (
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
        </section>
      </SimpleGrid>
    </>
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
