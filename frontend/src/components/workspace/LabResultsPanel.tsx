'use client';

import { useState } from 'react';
import { notifications } from '@mantine/notifications';
import { LabExecuteResponse, LabQueryHistoryResponse, DatabaseState, LabTask, LabTaskProgress, DB_RESET_SENTINEL } from '@/types/lab.types';
import { LabQueryReviewResponse } from '@/services/chatbot.service';
import { QueryReviewCard } from './QueryReviewCard';
import { LabChatTab } from './LabChatTab';

/* ── SVG icons ── */
const IconCheck = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);
const IconChevronDown = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="6 9 12 15 18 9"/>
  </svg>
);
const IconChevronRight = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="9 18 15 12 9 6"/>
  </svg>
);
const IconCopy = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
  </svg>
);
const IconPlay = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="5 3 19 12 5 21 5 3"/>
  </svg>
);
const IconDatabase = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
  </svg>
);
const IconRefreshSmall = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
  </svg>
);

interface LabResultsPanelProps {
  result: LabExecuteResponse | null;
  attempts: LabQueryHistoryResponse[];
  databaseState: DatabaseState | null;
  isLoadingDatabase: boolean;
  isStaffMode: boolean;
  tasks: LabTask[];
  currentQuery: string;
  taskProgress: Record<number, LabTaskProgress>;
  onAssignToTask: (taskId: number, query: string) => Promise<void>;
  onSubmitToTask: (taskId: number) => Promise<void>;
  reviewMode?: boolean;
  onRerunQuery?: (query: string) => Promise<void>;
  isExecuting?: boolean;
  onCopyQuery?: (query: string) => void;
  // AI Query Review
  lastReviewData?: LabQueryReviewResponse | null;
  isReviewing?: boolean;
  labId?: number;
  sessionId?: number | null;
}

export function LabResultsPanel({
  result,
  attempts,
  databaseState,
  isLoadingDatabase,
  isStaffMode,
  tasks,
  currentQuery,
  taskProgress,
  onAssignToTask,
  onSubmitToTask,
  reviewMode = false,
  onRerunQuery,
  isExecuting = false,
  onCopyQuery,
  lastReviewData,
  isReviewing = false,
  labId,
  sessionId,
}: LabResultsPanelProps) {
  const [activeTab, setActiveTab] = useState('results');
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());
  const [selectedTaskId, setSelectedTaskId] = useState<string>('');
  const [isAssigning, setIsAssigning] = useState(false);
  const [selectedSubmitTaskId, setSelectedSubmitTaskId] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toggleTable = (tableName: string) => {
    const newExpanded = new Set(expandedTables);
    if (newExpanded.has(tableName)) newExpanded.delete(tableName);
    else newExpanded.add(tableName);
    setExpandedTables(newExpanded);
  };

  const handleAssignAnswer = async () => {
    if (!selectedTaskId || !currentQuery.trim()) {
      notifications.show({ title: 'Validation Error', message: 'Please select a task', color: 'yellow' });
      return;
    }
    setIsAssigning(true);
    try {
      await onAssignToTask(parseInt(selectedTaskId), currentQuery);
      setSelectedTaskId('');
    } finally {
      setIsAssigning(false);
    }
  };

  const handleSubmitAnswer = async () => {
    if (!selectedSubmitTaskId) {
      notifications.show({ title: 'Validation Error', message: 'Please select a task', color: 'yellow' });
      return;
    }
    setIsSubmitting(true);
    try {
      await onSubmitToTask(parseInt(selectedSubmitTaskId));
      setSelectedSubmitTaskId('');
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedTaskHasAnswer = selectedTaskId
    ? tasks.find(t => t.id.toString() === selectedTaskId)?.has_answer ?? false
    : false;

  const tasksWithAnswers = tasks.filter(task => task.has_answer);
  const hasVisibleResultRows = result?.success === true && result.results.length > 0;

  const tabs = [
    { id: 'results', label: 'Results' },
    { id: 'history', label: `History${attempts.length > 0 ? ` (${attempts.length})` : ''}` },
    { id: 'database', label: `Database${databaseState && databaseState.tables.length > 0 ? ` (${databaseState.tables.length})` : ''}` },
    { id: 'ai-tutor', label: 'AI Tutor' },
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
          ) : (
            <div style={{ padding: 12, display: 'grid', gap: 12 }}>
              {/* Result meta */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>Results</span>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <span className={`badge ${result.success ? 'badge-success' : 'badge-danger'}`}>
                    {result.success ? 'Success' : 'Failed'}
                  </span>
                  {result.success && <span className="badge badge-info">{result.row_count} rows</span>}
                  <span className="badge neutral">{result.execution_time_ms.toFixed(2)}ms</span>
                </div>
              </div>

              {/* Assign to Task (Staff) */}
              {isStaffMode && !reviewMode && result.success && (
                hasVisibleResultRows ? (
                  <div className="card" style={{ padding: 12, background: 'var(--surface-brand)' }}>
                    <p style={{ margin: '0 0 10px', fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Assign to Task
                    </p>
                    <div style={{ display: 'grid', gap: 8 }}>
                      <p style={{ margin: 0, fontSize: 12, color: 'var(--brand-charcoal)' }}>
                        Assign this query result as the correct answer for a task
                      </p>
                      {tasks.length === 0 ? (
                      <div className="da-alert alert-info" style={{ fontSize: 12 }}>
                        No tasks exist yet. Create a task in the Tasks tab first.
                      </div>
                    ) : (
                      <>
                        <select
                          className="da-select"
                          style={{ width: '100%', fontSize: 13 }}
                          value={selectedTaskId}
                          onChange={(e) => setSelectedTaskId(e.target.value)}
                        >
                          <option value="">Choose a task to assign answer</option>
                          {tasks.map(task => (
                            <option key={task.id} value={task.id.toString()}>
                              {task.title}{task.has_answer ? ' ✓' : ''}
                            </option>
                          ))}
                        </select>
                        {selectedTaskHasAnswer && (
                          <div className="da-alert alert-warn" style={{ fontSize: 12 }}>
                            This task already has a correct answer. Proceeding will overwrite it.
                          </div>
                        )}
                        <button
                          className="btn btn-brand"
                          style={{ width: '100%', justifyContent: 'center', minHeight: 34 }}
                          onClick={handleAssignAnswer}
                          disabled={!selectedTaskId || isAssigning}
                        >
                          <IconCheck />
                          {isAssigning ? 'Assigning…' : selectedTaskHasAnswer ? 'Update Answer' : 'Assign Answer'}
                        </button>
                      </>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="card" style={{ padding: 12, background: 'var(--surface-brand)' }}>
                    <div className="da-alert alert-info" style={{ fontSize: 12 }}>
                      This query must return at least one visible row before it can be assigned to a Task.
                    </div>
                  </div>
                )
              )}

              {/* Submit to Task (Student) */}
              {!isStaffMode && result.success && (
                <div className="card" style={{ padding: 12, background: '#eff6ff' }}>
                  <p style={{ margin: '0 0 10px', fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Submit to Task
                  </p>
                  <div style={{ display: 'grid', gap: 8 }}>
                    <p style={{ margin: 0, fontSize: 12, color: 'var(--brand-charcoal)' }}>
                      Submit this result as your answer to a task
                    </p>
                    {tasksWithAnswers.length === 0 ? (
                      <div className="da-alert alert-info" style={{ fontSize: 12 }}>
                        No tasks available for submission yet.
                      </div>
                    ) : (
                      <>
                        <select
                          className="da-select"
                          style={{ width: '100%', fontSize: 13 }}
                          value={selectedSubmitTaskId}
                          onChange={(e) => setSelectedSubmitTaskId(e.target.value)}
                        >
                          <option value="">Choose a task to submit for</option>
                          {tasksWithAnswers.map(task => (
                            <option key={task.id} value={task.id.toString()}>
                              {task.title}{taskProgress[task.id]?.is_completed ? ' ✓' : ''}
                            </option>
                          ))}
                        </select>
                        {selectedSubmitTaskId && taskProgress[parseInt(selectedSubmitTaskId)]?.is_completed && (
                          <div className="da-alert" style={{ background: '#dcfce7', borderColor: '#bbf7d0', color: '#166534', fontSize: 12 }}>
                            You&apos;ve already solved this task! You can still resubmit.
                          </div>
                        )}
                        <button
                          className="btn btn-brand"
                          style={{ width: '100%', justifyContent: 'center', minHeight: 34 }}
                          onClick={handleSubmitAnswer}
                          disabled={!selectedSubmitTaskId || isSubmitting}
                        >
                          <IconCheck />
                          {isSubmitting ? 'Submitting…' : 'Submit Answer'}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* Error message */}
              {!result.success && result.error_message && (
                <div className="da-alert alert-error" role="alert">
                  <strong>Query Error</strong>
                  <span>{result.error_message}</span>
                </div>
              )}

              {/* Result table */}
              {result.success && result.results.length > 0 && (
                <div className="table-wrap">
                  <table className="da-table">
                    <thead>
                      <tr>
                        {result.columns.map(col => <th key={col}>{col}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {result.results.map((row, idx) => (
                        <tr key={idx}>
                          {result.columns.map(col => (
                            <td key={col}>
                              {row[col] === null ? 'NULL' : typeof row[col] === 'object' ? JSON.stringify(row[col]) : String(row[col])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {result.success && result.results.length === 0 && (
                <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>
                  Query executed successfully. No rows returned.
                </p>
              )}

              {/* AI Query Review Card — students only, shown after wrong task submission */}
              {!isStaffMode && !reviewMode && (isReviewing || lastReviewData) && (
                <QueryReviewCard
                  query={currentQuery}
                  isLoading={isReviewing}
                  problemToken={lastReviewData?.problem_token ?? ''}
                  explanation={lastReviewData?.explanation ?? ''}
                  hint={lastReviewData?.hint ?? ''}
                  dbStateIssue={lastReviewData?.db_state_issue}
                  dbStateMessage={lastReviewData?.db_state_message}
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
                No query history yet. Execute queries to see them here.
              </p>
            ) : (
              attempts.map(attempt => {
                /* ── Database Reset sentinel card ── */
                if (attempt.query === DB_RESET_SENTINEL) {
                  return (
                    <div
                      key={attempt.id}
                      className="card"
                      style={{
                        padding: '10px 12px',
                        borderLeft: '3px solid #f59e0b',
                        background: 'rgba(245,158,11,0.07)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ color: '#d97706' }}><IconRefreshSmall /></span>
                          <span style={{ fontSize: 13, fontWeight: 700, color: '#92400e' }}>Database Reset</span>
                          <span className="badge" style={{ background: '#fef3c7', color: '#92400e', border: '1px solid #fcd34d' }}>Reset</span>
                        </div>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#d97706' }}>
                          <IconDatabase />
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: 11, color: 'var(--text-muted)' }}>
                        {new Date(attempt.submitted_at).toLocaleString()}
                      </p>
                      <p style={{ margin: '4px 0 0', fontSize: 12, color: '#92400e' }}>
                        Database was restored to the original template at this point.
                      </p>
                    </div>
                  );
                }

                /* ── Normal query card ── */
                return (
                  <div key={attempt.id} className="card" style={{ padding: '10px 12px' }}>
                    {/* Header row */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <span className={`badge ${attempt.success ? 'badge-success' : 'badge-danger'}`}>
                          {attempt.success ? 'Success' : 'Failed'}
                        </span>
                        {attempt.success && <span className="badge badge-info">{attempt.row_count} rows</span>}
                        <span className="badge neutral">{attempt.execution_time_ms.toFixed(2)}ms</span>
                      </div>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {onCopyQuery && (
                          <button
                            className="icon-btn"
                            style={{ color: 'var(--text-muted)' }}
                            title="Copy query to editor"
                            onClick={() => {
                              onCopyQuery(attempt.query);
                              notifications.show({ title: 'Query Copied', message: 'Query loaded into editor', color: 'blue' });
                            }}
                          >
                            <IconCopy />
                          </button>
                        )}
                        {onRerunQuery && (
                          <button
                            className="icon-btn"
                            style={{ color: 'var(--info)', opacity: isExecuting ? 0.5 : 1 }}
                            title="Rerun this query"
                            onClick={() => onRerunQuery(attempt.query)}
                            disabled={isExecuting}
                          >
                            <IconPlay />
                          </button>
                        )}
                      </div>
                    </div>

                    <p style={{ margin: '0 0 4px', fontSize: 11, color: 'var(--text-muted)' }}>
                      {new Date(attempt.submitted_at).toLocaleString()}
                    </p>

                    <pre style={{
                      margin: 0, fontSize: 12, lineHeight: 1.5,
                      background: 'var(--surface-muted)', color: 'var(--text)',
                      padding: '6px 8px', borderRadius: 'var(--radius)',
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                      fontFamily: 'var(--font-geist-mono)',
                    }}>
                      {attempt.query.length > 150 ? `${attempt.query.substring(0, 150)}...` : attempt.query}
                    </pre>

                    {!attempt.success && attempt.error_message && (
                      <div className="da-alert alert-error" style={{ marginTop: 6, fontSize: 12 }}>
                        {attempt.error_message}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* ── Database Tab ── */}
        {activeTab === 'database' && (
          isLoadingDatabase ? (
            <div className="loading-center" style={{ minHeight: 120 }}>
              <div className="spinner" style={{ width: 20, height: 20 }} />
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Loading database state…</span>
            </div>
          ) : !databaseState ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13 }}>
              No database state available
            </div>
          ) : databaseState.tables.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13 }}>
              No tables in database
            </div>
          ) : (
            <div style={{ padding: 12, display: 'grid', gap: 8 }}>
              {databaseState.tables.map(table => (
                <div key={table.name} className="card" style={{ padding: 0, overflow: 'hidden' }}>
                  {/* Table header - always visible */}
                  <button
                    style={{
                      width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '10px 12px', textAlign: 'left',
                    }}
                    onClick={() => toggleTable(table.name)}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
                        {expandedTables.has(table.name) ? <IconChevronDown /> : <IconChevronRight />}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--text)' }}>{table.name}</span>
                    </div>
                    <span className="badge badge-info">{table.row_count} rows</span>
                  </button>

                  {/* Collapsed: column names */}
                  {!expandedTables.has(table.name) && (
                    <p style={{ margin: 0, padding: '0 12px 10px', fontSize: 11, color: 'var(--text-muted)' }}>
                      {table.columns.map(col => col.name).join(', ')}
                    </p>
                  )}

                  {/* Expanded: schema + data */}
                  {expandedTables.has(table.name) && (
                    <div style={{ padding: '0 12px 12px', display: 'grid', gap: 10 }}>
                      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />
                      <p style={{ margin: 0, fontSize: 11, fontWeight: 700, color: 'var(--brand-charcoal)' }}>Schema:</p>
                      <pre style={{
                        margin: 0, fontSize: 11, lineHeight: 1.5,
                        background: '#1e1e1e', color: '#d4d4d4',
                        padding: '8px 10px', borderRadius: 'var(--radius)',
                        overflow: 'auto', fontFamily: 'var(--font-geist-mono)',
                      }}>
                        {table.columns.map(col =>
                          `${col.name} ${col.type}${col.pk ? ' PRIMARY KEY' : ''}${col.notnull ? ' NOT NULL' : ''}`
                        ).join('\n')}
                      </pre>

                      {table.sample_data.rows.length > 0 && (
                        <>
                          <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />
                          <p style={{ margin: 0, fontSize: 11, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
                            Data Preview ({table.sample_data.rows.length} of {table.row_count} rows):
                          </p>
                          <div className="table-wrap" style={{ overflowX: 'auto' }}>
                            <table className="da-table" style={{ fontSize: 11 }}>
                              <thead>
                                <tr>
                                  {table.sample_data.columns.map(col => <th key={col}>{col}</th>)}
                                </tr>
                              </thead>
                              <tbody>
                                {table.sample_data.rows.map((row, idx) => (
                                  <tr key={idx}>
                                    {table.sample_data.columns.map(col => (
                                      <td key={col}>
                                        {row[col] === null ? 'NULL' : typeof row[col] === 'object' ? JSON.stringify(row[col]) : String(row[col])}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        )}
        {/* ── AI Tutor Tab ── */}
        {activeTab === 'ai-tutor' && (
          labId && sessionId ? (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
              <LabChatTab labId={labId} sessionId={sessionId} />
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13, padding: 24, textAlign: 'center' }}>
              AI Tutor is not available in this mode.
            </div>
          )
        )}
      </div>
    </div>
  );
}
