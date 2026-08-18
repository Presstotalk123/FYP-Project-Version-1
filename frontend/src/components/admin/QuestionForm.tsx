'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import dynamic from 'next/dynamic';

const Editor = dynamic(() => import('@monaco-editor/react'), { ssr: false });
import { QuestionDetail, Difficulty } from '@/types/question.types';
import api from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { MarkdownDescriptionField } from '@/components/common/MarkdownDescriptionField';
import { ladService } from '@/services/lad.service';
import { Concept } from '@/types/lad.types';
import { detectConcepts } from '@/utils/sqlConcepts';
import { mysqlToSqlite } from '@/utils/sqlDialect';

interface QuestionFormProps {
  question?: QuestionDetail;
  isEdit?: boolean;
}

const labelStyle: React.CSSProperties = { fontSize: 13, fontWeight: 700, color: 'var(--brand-charcoal)' };
const helpStyle: React.CSSProperties = { margin: 0, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const editorFrame: React.CSSProperties = { border: '1px solid var(--border-strong)', borderRadius: 'var(--radius)', overflow: 'hidden' };

const editorOptions = {
  minimap: { enabled: false },
  fontSize: 13,
  lineNumbers: 'on' as const,
  scrollBeyondLastLine: false,
};

// Rewrites the editor's MySQL/LeetCode-style script to SQLite in place. Only enabled when
// there's something to convert. Best-effort (see mysqlToSqlite) — the author reviews after.
function ConvertToSqliteButton({ value, onConvert }: { value: string; onConvert: (v: string) => void }) {
  return (
    <button
      type="button"
      className="btn btn-secondary"
      style={{ minHeight: 28, padding: '0 10px', fontSize: 12 }}
      onClick={() => onConvert(mysqlToSqlite(value))}
      disabled={!value.trim()}
      title="Rewrite MySQL / LeetCode syntax (TRUNCATE, int, varchar…) to SQLite. Ctrl+Z to undo."
    >
      Convert to SQLite
    </button>
  );
}

// Label row that carries the Convert button on the right (used for the SQL setup editors).
const labelRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
};

export function QuestionForm({ question, isEdit = false }: QuestionFormProps) {
  const router = useRouter();

  // Form state
  const [title, setTitle] = useState(question?.title || '');
  const [description, setDescription] = useState(question?.description || '');
  const [difficulty, setDifficulty] = useState<string>(question?.difficulty || 'easy');
  const [schemaSql, setSchemaSql] = useState(question?.schema_sql || '');
  const [sampleDataSql, setSampleDataSql] = useState(question?.sample_data_sql || '');
  const [correctAnswerQuery, setCorrectAnswerQuery] = useState(question?.correct_answer_query || '');
  const [advancedSqlTesting, setAdvancedSqlTesting] = useState(question?.advanced_sql_testing ?? false);
  const [testScript, setTestScript] = useState(question?.test_script || '');
  const [checkQuery, setCheckQuery] = useState(question?.check_query || '');
  const [orderSensitive, setOrderSensitive] = useState(question?.order_sensitive ?? false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Concept tagging (Learning Analytics). Best-effort: if the taxonomy isn't
  // seeded / the endpoint is unavailable, the section simply doesn't render.
  const [concepts, setConcepts] = useState<Concept[]>([]);
  // concept_id -> weight for the tags selected on this question.
  const [conceptTags, setConceptTags] = useState<Record<number, number>>({});

  useEffect(() => {
    let cancelled = false;
    ladService
      .listConcepts()
      .then((list) => {
        if (!cancelled) setConcepts(list);
      })
      .catch(() => {
        /* taxonomy unavailable — hide the section */
      });
    if (isEdit && question) {
      ladService
        .getQuestionConcepts(question.id)
        .then((tags) => {
          if (cancelled) return;
          const map: Record<number, number> = {};
          for (const t of tags) map[t.concept_id] = t.weight;
          setConceptTags(map);
        })
        .catch(() => {
          /* no existing tags */
        });
    }
    return () => {
      cancelled = true;
    };
  }, [isEdit, question]);

  const toggleConcept = (conceptId: number) => {
    setConceptTags((prev) => {
      const next = { ...prev };
      if (conceptId in next) delete next[conceptId];
      else next[conceptId] = 1.0;
      return next;
    });
  };

  const setConceptWeight = (conceptId: number, weight: number) => {
    setConceptTags((prev) => ({ ...prev, [conceptId]: weight }));
  };

  // Suggest concept tags from the answer query (best-effort keyword heuristics —
  // see utils/sqlConcepts). Additive only: fills in concepts not already selected,
  // with a default salience weight, and never overwrites the author's own picks.
  const suggestConceptsFromQuery = () => {
    const slugToId: Record<string, number> = {};
    for (const c of concepts) slugToId[c.slug] = c.id;

    const additions: Record<number, number> = {};
    for (const { slug, weight } of detectConcepts(correctAnswerQuery)) {
      const id = slugToId[slug];
      if (id != null && !(id in conceptTags)) additions[id] = weight;
    }

    const added = Object.keys(additions).length;
    if (added > 0) setConceptTags((prev) => ({ ...prev, ...additions }));
    notifications.show({
      title: added > 0 ? `Added ${added} concept${added === 1 ? '' : 's'}` : 'No new concepts',
      message:
        added > 0
          ? 'Review the suggested tags and weights before saving.'
          : 'The answer query matched no new concepts (already tagged, or none detected).',
      color: added > 0 ? 'green' : 'gray',
    });
  };

  const persistConceptTags = async (questionId: number) => {
    // Best-effort — a tagging failure must not fail the question save itself.
    try {
      const tags = Object.entries(conceptTags).map(([cid, weight]) => ({
        concept_id: Number(cid),
        weight,
      }));
      await ladService.setQuestionConcepts(questionId, tags);
    } catch {
      notifications.show({
        title: 'Concept tags not saved',
        message: 'The question was saved, but its concept tags could not be updated.',
        color: 'yellow',
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!title.trim()) {
      setError('Title is required');
      return;
    }
    if (!description.trim()) {
      setError('Description is required');
      return;
    }
    if (!schemaSql.trim()) {
      setError('Schema SQL is required');
      return;
    }
    if (!sampleDataSql.trim()) {
      setError('Sample Data SQL is required');
      return;
    }
    if (!correctAnswerQuery.trim()) {
      setError('Correct Answer Query is required');
      return;
    }
    if (advancedSqlTesting && !testScript.trim()) {
      setError('Test Script is required when Advanced SQL Testing is enabled');
      return;
    }
    if (advancedSqlTesting && !checkQuery.trim()) {
      setError('Check Query is required when Advanced SQL Testing is enabled');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = {
        title,
        description,
        difficulty: difficulty as Difficulty,
        schema_sql: schemaSql,
        sample_data_sql: sampleDataSql,
        correct_answer_query: correctAnswerQuery,
        advanced_sql_testing: advancedSqlTesting,
        test_script: advancedSqlTesting ? testScript : null,
        check_query: advancedSqlTesting ? checkQuery : null,
        // Row-order grading is a standard-mode concept; advanced mode ignores it.
        order_sensitive: advancedSqlTesting ? false : orderSensitive,
      };

      if (isEdit && question) {
        // Update existing question
        await api.put(API_ENDPOINTS.QUESTIONS.DETAIL(question.id), payload);
        await persistConceptTags(question.id);
        notifications.show({
          title: 'Success',
          message: 'Question updated successfully',
          color: 'green',
        });
      } else {
        // Create new question
        const created = await api.post<{ id: number }>(API_ENDPOINTS.QUESTIONS.BASE, payload);
        if (created.data?.id) await persistConceptTags(created.data.id);
        notifications.show({
          title: 'Success',
          message: 'Question created successfully',
          color: 'green',
        });
      }

      router.push('/admin/questions');
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      const errorMessage = error.response?.data?.detail ||
        `Failed to ${isEdit ? 'update' : 'create'} question`;
      setError(errorMessage);
      notifications.show({
        title: 'Error',
        message: errorMessage,
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 20 }}>
      {/* Error alert */}
      {error && (
        <div className="da-alert alert-error" role="alert">
          <strong>Error</strong>
          <span>{error}</span>
        </div>
      )}

      {/* Title */}
      <div style={{ display: 'grid', gap: 6 }}>
        <label htmlFor="question-title" style={labelStyle}>
          Question Title <span style={{ color: 'var(--error)' }}>*</span>
        </label>
        <input
          id="question-title"
          className="da-input"
          style={{ width: '100%' }}
          type="text"
          placeholder="Enter question title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
      </div>

      {/* Description */}
      <MarkdownDescriptionField
        id="question-description"
        label="Description"
        required
        placeholder="Enter question description"
        value={description}
        onChange={setDescription}
      />

      {/* Difficulty */}
      <div style={{ display: 'grid', gap: 6 }}>
        <label htmlFor="question-difficulty" style={labelStyle}>
          Difficulty <span style={{ color: 'var(--error)' }}>*</span>
        </label>
        <select
          id="question-difficulty"
          className="da-select"
          style={{ width: '100%' }}
          value={difficulty}
          onChange={(e) => setDifficulty(e.target.value)}
        >
          <option value="easy">Easy</option>
          <option value="medium">Medium</option>
          <option value="hard">Hard</option>
        </select>
      </div>

      {/* Schema SQL */}
      <div style={{ display: 'grid', gap: 6 }}>
        <div style={labelRowStyle}>
          <label style={labelStyle}>
            Schema SQL <span style={{ color: 'var(--error)' }}>*</span>
          </label>
          <ConvertToSqliteButton value={schemaSql} onConvert={setSchemaSql} />
        </div>
        <div style={editorFrame}>
          <Editor
            height="200px"
            language="sql"
            theme="vs-dark"
            value={schemaSql}
            onChange={(value) => setSchemaSql(value || '')}
            options={editorOptions}
          />
        </div>
      </div>

      {/* Sample Data SQL */}
      <div style={{ display: 'grid', gap: 6 }}>
        <div style={labelRowStyle}>
          <label style={labelStyle}>
            Sample Data SQL <span style={{ color: 'var(--error)' }}>*</span>
          </label>
          <ConvertToSqliteButton value={sampleDataSql} onConvert={setSampleDataSql} />
        </div>
        <div style={editorFrame}>
          <Editor
            height="200px"
            language="sql"
            theme="vs-dark"
            value={sampleDataSql}
            onChange={(value) => setSampleDataSql(value || '')}
            options={editorOptions}
          />
        </div>
      </div>

      {/* Correct Answer Query / Reference Implementation */}
      <div style={{ display: 'grid', gap: 6 }}>
        <label style={labelStyle}>
          {advancedSqlTesting ? 'Reference Implementation' : 'Correct Answer Query'} <span style={{ color: 'var(--error)' }}>*</span>
        </label>
        <p style={helpStyle}>
          {advancedSqlTesting
            ? 'The correct SQL for this question, e.g. a CREATE TRIGGER statement.'
            : 'A SELECT query whose output is the expected answer.'}
        </p>
        <div style={editorFrame}>
          <Editor
            height="150px"
            language="sql"
            theme="vs-dark"
            value={correctAnswerQuery}
            onChange={(value) => setCorrectAnswerQuery(value || '')}
            options={editorOptions}
          />
        </div>
      </div>

      {/* Advanced SQL Testing toggle */}
      <div style={{ display: 'grid', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            role="switch"
            aria-checked={advancedSqlTesting}
            aria-label="Advanced SQL Testing"
            onClick={() => setAdvancedSqlTesting((v) => !v)}
            style={{
              position: 'relative', width: 40, height: 22, borderRadius: 999,
              border: 'none', cursor: 'pointer', flexShrink: 0, padding: 0,
              background: advancedSqlTesting ? 'var(--brand-lilac)' : 'var(--border-strong)',
              transition: 'background 140ms ease',
            }}
          >
            <span style={{
              position: 'absolute', top: 2, left: advancedSqlTesting ? 20 : 2,
              width: 18, height: 18, borderRadius: '50%', background: '#fff',
              boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
              transition: 'left 140ms ease',
            }} />
          </button>
          <span style={labelStyle}>Advanced SQL Testing</span>
        </div>
        <p style={helpStyle}>
          For triggers and complex multi-statement DML only. Stored procedures
          and SQL-level functions are not supported on this platform (SQLite
          has no CREATE PROCEDURE / CREATE FUNCTION). When enabled, grading
          applies the submission, runs a hidden Test Script, runs a hidden
          Check Query, and compares its hashed output — instead of comparing
          the submission&apos;s own output directly.
        </p>
      </div>

      {/* Order-sensitive grading toggle (standard mode only) */}
      {!advancedSqlTesting && (
        <div style={{ display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button
              type="button"
              role="switch"
              aria-checked={orderSensitive}
              aria-label="Order-sensitive grading"
              onClick={() => setOrderSensitive((v) => !v)}
              style={{
                position: 'relative', width: 40, height: 22, borderRadius: 999,
                border: 'none', cursor: 'pointer', flexShrink: 0, padding: 0,
                background: orderSensitive ? 'var(--brand-lilac)' : 'var(--border-strong)',
                transition: 'background 140ms ease',
              }}
            >
              <span style={{
                position: 'absolute', top: 2, left: orderSensitive ? 20 : 2,
                width: 18, height: 18, borderRadius: '50%', background: '#fff',
                boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
                transition: 'left 140ms ease',
              }} />
            </button>
            <span style={labelStyle}>Order-sensitive grading</span>
          </div>
          <p style={helpStyle}>
            Require students&apos; rows in the exact order your correct query
            returns them (enforces <code>ORDER BY</code>). Off by default — row
            order is ignored during comparison.
          </p>
        </div>
      )}

      {advancedSqlTesting && (
        <>
          {/* Test Script */}
          <div style={{ display: 'grid', gap: 6 }}>
            <label style={labelStyle}>
              Test Script <span style={{ color: 'var(--error)' }}>*</span>
            </label>
            <p style={helpStyle}>
              Hidden from students. One or more statements that exercise the
              submission, e.g. an INSERT that should fire the trigger.
            </p>
            <div style={editorFrame}>
              <Editor
                height="150px"
                language="sql"
                theme="vs-dark"
                value={testScript}
                onChange={(value) => setTestScript(value || '')}
                options={editorOptions}
              />
            </div>
          </div>

          {/* Check Query */}
          <div style={{ display: 'grid', gap: 6 }}>
            <label style={labelStyle}>
              Check Query <span style={{ color: 'var(--error)' }}>*</span>
            </label>
            <p style={helpStyle}>
              Hidden from students. A single SELECT that captures the
              resulting database state after the Test Script runs.
            </p>
            <div style={editorFrame}>
              <Editor
                height="150px"
                language="sql"
                theme="vs-dark"
                value={checkQuery}
                onChange={(value) => setCheckQuery(value || '')}
                options={editorOptions}
              />
            </div>
          </div>
        </>
      )}

      {/* Concept tags (Learning Analytics) */}
      {concepts.length > 0 && (
        <div style={{ display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <span style={labelStyle}>SQL Concepts</span>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={suggestConceptsFromQuery}
              disabled={!correctAnswerQuery.trim()}
              style={{ padding: '4px 10px', fontSize: 12 }}
            >
              ✨ Suggest from answer query
            </button>
          </div>
          <p style={helpStyle}>
            Tag the SQL concepts this question exercises. These drive per-concept mastery
            tracking and the student learning dashboard. Weights (default 1.0) let one
            concept count more than another for a question. Use <strong>Suggest from answer
            query</strong> to auto-detect concepts and weights from the correct answer —
            it only adds concepts you haven&apos;t already picked, so review before saving.
          </p>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
              gap: 8,
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius)',
              padding: 12,
              maxHeight: 260,
              overflowY: 'auto',
            }}
          >
            {concepts.map((c) => {
              const selected = c.id in conceptTags;
              return (
                <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleConcept(c.id)}
                    />
                    <span>{c.display_name}</span>
                  </label>
                  {selected && (
                    <input
                      type="number"
                      className="da-input"
                      aria-label={`${c.display_name} weight`}
                      value={conceptTags[c.id]}
                      min={0.1}
                      max={5}
                      step={0.1}
                      onChange={(e) => setConceptWeight(c.id, Number(e.target.value) || 1.0)}
                      style={{ width: 64, marginLeft: 'auto', padding: '2px 6px', fontSize: 12 }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="button-row" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => router.push('/admin/problems')}
          disabled={loading}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-brand"
          disabled={loading}
        >
          {loading ? 'Saving…' : (isEdit ? 'Update Question' : 'Create Question')}
        </button>
      </div>
    </form>
  );
}
