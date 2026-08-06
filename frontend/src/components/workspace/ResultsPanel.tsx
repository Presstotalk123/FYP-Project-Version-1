'use client';

import { useState, useEffect } from 'react';
import { ExecuteResponse, Attempt } from '@/types/attempt.types';
import { QuestionDetail } from '@/types/question.types';
import { ChatTab } from './ChatTab';
import { QueryReviewCard } from './QueryReviewCard';
import { chatbotService, QueryReviewResponse } from '@/services/chatbot.service';

/* ── SVG icons ── */
const IconCheck = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);
const IconX = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
  </svg>
);

interface ResultsPanelProps {
  result: ExecuteResponse | null;
  attempts: Attempt[];
  onRefreshHistory: () => void;
  questionId: number;
  question: QuestionDetail;
  currentQuery: string;
}

export function ResultsPanel({
  result,
  attempts,
  questionId,
  question,
  currentQuery,
}: ResultsPanelProps) {
  const [activeTab, setActiveTab] = useState('results');
  const [reviewData, setReviewData] = useState<QueryReviewResponse | null>(null);
  const [isReviewing, setIsReviewing] = useState(false);

  // When on, students never see correct/incorrect — just a neutral "Submitted" state.
  const hideCorrectness = question.hide_correctness;

  // Auto-trigger AI review whenever we get a wrong (but valid) result
  useEffect(() => {
    // Never trigger review when correctness is hidden — is_correct is null and a
    // review card would itself reveal that the answer was wrong.
    if (hideCorrectness) {
      setReviewData(null);
      return;
    }
    // Clear card on correct result, SQL error, or no result
    if (!result || result.is_correct || result.error_message) {
      setReviewData(null);
      return;
    }

    // Wrong-but-valid query → trigger review
    setReviewData(null);
    setIsReviewing(true);

    chatbotService
      .reviewQuery(questionId, currentQuery)
      .then(setReviewData)
      .catch(() => {}) // fail silently — never break the results view
      .finally(() => setIsReviewing(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const tabs = [
    { id: 'results', label: 'Results' },
    { id: 'history', label: `History${attempts.length > 0 ? ` (${attempts.length})` : ''}` },
    { id: 'chat', label: 'Bagheera' },
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Tab bar */}
      <div className="tabs" style={{ margin: 0, padding: '0 12px', flexShrink: 0 }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: 'auto' }}>

        {/* ── Results Tab ── */}
        {activeTab === 'results' && (
          !result ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13 }}>
              Run a query to see results
            </div>
          ) : result.error_message ? (
            <div style={{ padding: 12 }}>
              <div className="da-alert alert-error" role="alert">
                <strong>Error</strong>
                <span>{result.error_message}</span>
              </div>
            </div>
          ) : (
            <div style={{ padding: 12, display: 'grid', gap: 12 }}>
              {/* Correctness alert */}
              {hideCorrectness ? (
                <div className="da-alert alert-info" role="status">
                  <strong style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <IconCheck /> Submitted
                  </strong>
                  <span>Your query was submitted successfully.</span>
                </div>
              ) : result.is_correct ? (
                <div className="da-alert" role="status" style={{ background: '#dcfce7', borderColor: '#bbf7d0', color: '#166534' }}>
                  <strong style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <IconCheck /> Correct!
                  </strong>
                  <span>Your query returned the expected results.</span>
                </div>
              ) : (
                <div className="da-alert alert-error" role="alert">
                  <strong style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <IconX /> Incorrect
                  </strong>
                  <span>Your query results don&apos;t match the expected output.</span>
                </div>
              )}

              {/* Advanced SQL Testing grades on hidden state, not the submission's
                  own output — there's no query-result table to show. */}
              {!question.advanced_sql_testing && (
                <div style={{ display: 'grid', gap: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>Query Results</span>
                  <div className="table-wrap">
                    <table className="da-table">
                      <thead>
                        <tr>
                          {result.columns.map((col) => <th key={col}>{col}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {result.results.map((row, idx) => (
                          <tr key={idx}>
                            {result.columns.map((col) => (
                              <td key={col}>
                                {row[col] === null || row[col] === undefined
                                  ? 'NULL'
                                  : typeof row[col] === 'object'
                                    ? JSON.stringify(row[col])
                                    : String(row[col])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
                    {result.row_count} {result.row_count === 1 ? 'row' : 'rows'} returned
                  </p>
                </div>
              )}

              {/* AI Query Review Card — only for wrong-but-valid queries */}
              {(isReviewing || reviewData) && (
                <QueryReviewCard
                  query={currentQuery}
                  isLoading={isReviewing}
                  problemToken={reviewData?.problem_token ?? ''}
                  explanation={reviewData?.explanation ?? ''}
                  hint={reviewData?.hint ?? ''}
                />
              )}
            </div>
          )
        )}

        {/* ── History Tab ── */}
        {activeTab === 'history' && (
          <div style={{ padding: 12, display: 'grid', gap: 8 }}>
            {attempts.length === 0 ? (
              <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, padding: '24px 0' }}>
                No attempts yet for this question
              </p>
            ) : (
              attempts.map((attempt) => (
                <div key={attempt.id} className="card" style={{ padding: '10px 12px' }}>
                  {/* Header row */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
                    {hideCorrectness ? (
                      <span className="badge badge-info">Submitted</span>
                    ) : (
                      <span className={`badge ${attempt.is_correct ? 'badge-success' : 'badge-danger'}`}>
                        {attempt.is_correct ? 'Correct' : 'Incorrect'}
                      </span>
                    )}
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {new Date(attempt.submitted_at).toLocaleString()}
                    </span>
                  </div>

                  <pre style={{
                    margin: 0, fontSize: 12, lineHeight: 1.5,
                    background: 'var(--surface-muted)', color: 'var(--text)',
                    padding: '6px 8px', borderRadius: 'var(--radius)',
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    fontFamily: 'var(--font-geist-mono)',
                  }}>
                    {attempt.query.length > 150 ? `${attempt.query.substring(0, 150)}...` : attempt.query}
                  </pre>

                  {attempt.execution_time_ms && (
                    <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-muted)' }}>
                      Execution time: {attempt.execution_time_ms.toFixed(2)}ms
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* ── AI Tutor Tab ── */}
        {activeTab === 'chat' && (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <ChatTab
              questionId={questionId}
              question={question}
              currentQuery={currentQuery}
              result={result}
            />
          </div>
        )}
      </div>
    </div>
  );
}
