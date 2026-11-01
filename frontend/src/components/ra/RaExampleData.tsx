'use client';

import { useEffect, useRef, useState } from 'react';
import { raService } from '@/services/ra.service';
import { RaRelation } from '@/types/ra.types';
import { RaTable } from './RaTable';

export interface RaExamplePreview {
  sql: string;
  relations: RaRelation[];
}

/**
 * The example data students will see while the question's INSERT box is empty.
 * ``chosen`` is the example the question keeps (null = none chosen yet: it is then built
 * from the final model answers when the question is saved, and the preview follows the
 * model answers as staff type). A chosen example that no longer fits the schema is
 * dropped (``onChosen(null)``), as the server would on save.
 */
export function useRaExampleData(schemaSql: string, modelAnswers: string[], chosen: string | null,
  enabled: boolean, onChosen: (sql: string | null) => void) {
  const [preview, setPreview] = useState<RaExamplePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const variant = useRef(0);
  const onChosenRef = useRef(onChosen);
  useEffect(() => {
    onChosenRef.current = onChosen;
  }, [onChosen]);

  // A key, not the array: the form builds a new array on every render.
  const answersKey = modelAnswers.join('\u0000');
  useEffect(() => {
    if (!enabled || !schemaSql.trim()) {
      setPreview(null);
      setError(null);
      return;
    }
    let current = true;
    const timer = setTimeout(() => {
      setLoading(true);
      raService.exampleData(schemaSql, answersKey ? answersKey.split('\u0000') : [], 0, chosen)
        .then((r) => {
          if (!current) return;
          if (!r.ok) {
            setPreview(null);
            setError(r.error ? r.error.message : 'The example data could not be built.');
            return;
          }
          setError(null);
          setPreview({ sql: r.data_sql, relations: r.relations });
          if (chosen && r.data_sql !== chosen) onChosenRef.current(null);   // no longer fits the schema
        })
        .catch(() => { if (current) setError('Could not reach the server.'); })
        .finally(() => { if (current) setLoading(false); });
    }, 600);
    return () => { current = false; clearTimeout(timer); };
  }, [enabled, schemaSql, answersKey, chosen]);

  const regenerate = async () => {
    variant.current += 1;
    setLoading(true);
    try {
      const r = await raService.exampleData(schemaSql, modelAnswers, variant.current);
      if (r.ok) {
        setError(null);
        setPreview({ sql: r.data_sql, relations: r.relations });
        onChosenRef.current(r.data_sql);
      } else {
        setError(r.error ? r.error.message : 'The example data could not be built.');
      }
    } catch {
      setError('Could not reach the server.');
    } finally {
      setLoading(false);
    }
  };

  return { preview, error, loading, regenerate };
}

/** The staff form's view of the example data, with Regenerate and Copy into INSERT box. */
export function RaExampleDataPanel({ preview, error, loading, chosen, onRegenerate, onCopy, disabled }: {
  preview: RaExamplePreview | null;
  error: string | null;
  loading: boolean;
  chosen: boolean;
  onRegenerate: () => void;
  onCopy: (sql: string) => void;
  disabled: boolean;
}) {
  return (
    <div style={{ display: 'grid', gap: 10, padding: 12, border: '1px dashed var(--border-strong)', borderRadius: 'var(--radius)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 13 }}>Example data shown to students</strong>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>(the INSERT box is empty)</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button type="button" className="btn btn-secondary" style={{ minHeight: 30, padding: '0 10px', fontSize: 12 }}
            onClick={onRegenerate} disabled={disabled || loading || !preview}>
            {loading ? 'Building…' : 'Regenerate'}
          </button>
          <button type="button" className="btn btn-secondary" style={{ minHeight: 30, padding: '0 10px', fontSize: 12 }}
            onClick={() => preview && onCopy(preview.sql)} disabled={disabled || !preview}
            title="Put this data in the INSERT box to edit it by hand; it then becomes the question's own data">
            Copy into INSERT box ↑
          </button>
        </span>
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        Made up from the schema and the model answers: 3–5 tuples per relation with realistic-looking values,
        chosen so each model answer returns something. Students see it with the schema; Check and the feedback
        after Submit run on it. Grading still uses the generated test databases.{' '}
        {chosen ? 'This example is kept until you Regenerate it or the schema no longer accepts it.'
          : 'It is built again from the final model answers when you save.'}
      </span>
      {error && <div className="alert-error" style={{ fontSize: 13 }}>{error}</div>}
      {!preview && !error && (
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{loading ? 'Building…' : 'Write the CREATE TABLE statements to see it.'}</span>
      )}
      {preview && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, opacity: loading ? 0.6 : 1 }}>
          {preview.relations.map((rel) => (
            <div key={rel.name} style={{ minWidth: 160 }}>
              <RaTable caption={rel.name} columns={rel.columns} rows={rel.rows} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
