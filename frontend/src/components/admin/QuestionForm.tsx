'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import dynamic from 'next/dynamic';

const Editor = dynamic(() => import('@monaco-editor/react'), { ssr: false });
import { QuestionDetail, Difficulty } from '@/types/question.types';
import api from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { MarkdownDescriptionField } from '@/components/common/MarkdownDescriptionField';

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
        notifications.show({
          title: 'Success',
          message: 'Question updated successfully',
          color: 'green',
        });
      } else {
        // Create new question
        await api.post(API_ENDPOINTS.QUESTIONS.BASE, payload);
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
        <label style={labelStyle}>
          Schema SQL <span style={{ color: 'var(--error)' }}>*</span>
        </label>
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
        <label style={labelStyle}>
          Sample Data SQL <span style={{ color: 'var(--error)' }}>*</span>
        </label>
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
