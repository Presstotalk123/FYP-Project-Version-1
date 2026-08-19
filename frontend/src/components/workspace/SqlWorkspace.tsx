'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Box } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ExecuteResponse, Attempt } from '@/types/attempt.types';
import { questionService } from '@/services/question.service';
import { executeService } from '@/services/execute.service';
import { attemptService } from '@/services/attempt.service';
import { queryKeys } from '@/services/query-keys';
import { QuestionPanel } from './QuestionPanel';
import { EditorPanel } from './EditorPanel';
import { ResultsPanel } from './ResultsPanel';
import { AssessmentTimer } from '@/components/assessment/AssessmentTimer';
import { QuestionWeightBadge } from '@/components/assessment/QuestionWeightBadge';
import { QuestionNavigator } from '@/components/assessment/QuestionNavigator';
import { useAssessmentTimer } from '@/contexts/AssessmentTimerContext';
import { useAssessmentProgress } from '@/contexts/AssessmentProgressContext';
import { useRunCooldown } from '@/hooks/use-run-cooldown';

/* ── SVG icons ── */
const IconLogout = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
  </svg>
);

interface SqlWorkspaceProps {
  questionId: number;
  backUrl?: string;
  /** Assessment weightage (%) for this question; omitted outside assessments. */
  weight?: number;
  /** True when rendered inside an assessment; drives the cooldown tuning. */
  inAssessment?: boolean;
}

export function SqlWorkspace({ questionId, backUrl, weight, inAssessment = false }: SqlWorkspaceProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const timer = useAssessmentTimer();
  const progress = useAssessmentProgress();

  // State
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  // Per-question query cap (assessment SQL questions only). null = uncapped / not yet known.
  // Populated from the execute response after each run; a 403 also flips limitReached on.
  const [maxQueries, setMaxQueries] = useState<number | null>(null);
  const [attemptsUsed, setAttemptsUsed] = useState<number | null>(null);
  const [limitHit, setLimitHit] = useState(false);
  const limitReached =
    limitHit || (maxQueries != null && attemptsUsed != null && attemptsUsed >= maxQueries);

  // Lifted out of ResultsPanel so the editor can tell when the Bagheera chat tab
  // is open — it renders a "watching" ring around itself in that case.
  const [activeTab, setActiveTab] = useState('results');
  const isBagheeraActive = activeTab === 'chat';

  // Static question content — cached (see providers.tsx) so revisiting this
  // question (e.g. switching between assessment items) renders it instantly.
  const questionQuery = useQuery({
    queryKey: queryKeys.questionById(questionId),
    queryFn: () => questionService.getQuestionById(questionId),
  });
  const question = questionQuery.data ?? null;
  const loading = questionQuery.isLoading;
  const error = questionQuery.error
    ? ((questionQuery.error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load question')
    : null;

  // Cooldown to throttle rapid Run clicks. Scoped per question and persisted across
  // navigation/reload via sessionStorage. Assessments keep the progressive 3 → 10s → 20s
  // tiers; outside assessments the first 10 runs are free, then a flat 5s applies.
  const { isCoolingDown, registerRunComplete } = useRunCooldown(
    inAssessment
      ? { storageKey: `run-cooldown:sql:${questionId}` }
      : {
          freeLimit: 10,
          tier1Limit: 10,
          tier1Cooldown: 5,
          tier2Cooldown: 5,
          storageKey: `run-cooldown:sql:${questionId}`,
        },
  );

  // Resizable panel state
  const [leftPercent, setLeftPercent] = useState(30);
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [centerPercent, setCenterPercent] = useState(40);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

  // Attempts are live session state (not cached): fetch on mount so a revisit
  // always shows the student's latest history. The static question above loads
  // from cache instantly while this populates in the background.
  useEffect(() => {
    let cancelled = false;
    attemptService
      .getQuestionAttempts(questionId)
      .then((attemptsData) => {
        if (cancelled) return;
        setAttempts(attemptsData);
        if (attemptsData.length > 0) {
          progress.markAttempted();
        }
      })
      .catch(() => {
        // Non-critical — history simply stays empty if it fails to load.
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionId]);

  // Execute query
  const handleExecute = async () => {
    // Defensive guard: never run while a request is in flight or the cooldown is
    // active, even if the button somehow wasn't disabled.
    if (isExecuting || isCoolingDown) {
      return;
    }
    // The student has used up their allotted queries for this question.
    if (limitReached) {
      notifications.show({
        title: 'Query limit reached',
        message: 'You have reached the maximum number of queries allowed for this question.',
        color: 'red',
      });
      return;
    }
    if (!query.trim()) {
      notifications.show({
        title: 'Empty Query',
        message: 'Please enter a SQL query',
        color: 'yellow',
      });
      return;
    }

    setIsExecuting(true);
    // Pause the assessment countdown while the query runs; the backend credits this
    // time to the deadline and resume() picks up the new end_time from the response.
    timer.pause();
    let creditedEndTime: string | null | undefined;
    try {
      const response = await executeService.executeQuery({
        question_id: questionId,
        query,
      });
      creditedEndTime = response.assessment_end_time;
      setResult(response);
      // Track the per-question query cap so the UI can show "X of N used" and disable Run
      // once it's hit. Both fields are null when the question is uncapped.
      if (response.max_queries != null) {
        setMaxQueries(response.max_queries);
        setAttemptsUsed(response.attempts_used ?? null);
      }
      // The request round-tripped successfully — this counts as an attempt for the
      // navigator regardless of whether the query was correct or had a SQL error.
      progress.markAttempted();

      if (response.is_correct === null) {
        // Correctness is hidden for this question — show a neutral confirmation only.
        notifications.show({
          title: 'Submitted',
          message: 'Your query was submitted successfully',
          color: 'blue',
        });
      } else if (response.is_correct) {
        notifications.show({
          title: 'Correct!',
          message: 'Your query returned the expected results',
          color: 'green',
        });
      }

      // Refresh attempts
      const newAttempts = await attemptService.getQuestionAttempts(questionId);
      setAttempts(newAttempts);

      // The attempt changed this student's progress/completion — drop the cached
      // dashboard data so it re-fetches fresh on the next visit (prefix match
      // clears every difficulty/search variant of studentQuestions).
      queryClient.invalidateQueries({ queryKey: queryKeys.studentProgress });
      queryClient.invalidateQueries({ queryKey: ['studentQuestions'] });
    } catch (err) {
      const error = err as { response?: { status?: number; data?: { detail?: string } } };
      const detail = error.response?.data?.detail;
      // The server rejects a run over the cap with a 403; lock the editor so the student
      // can't keep trying. (Covers the reload case where the cap was hit in a prior session.)
      if (error.response?.status === 403 && detail?.includes('maximum number of queries')) {
        setLimitHit(true);
      }
      notifications.show({
        title: 'Execution Error',
        message: detail || 'Failed to execute query',
        color: 'red',
      });
    } finally {
      setIsExecuting(false);
      timer.resume(creditedEndTime);
      // Begin the cooldown after the request has completed (result returned).
      registerRunComplete();
    }
  };

  // Clear query
  const handleClear = () => {
    setQuery('');
  };

  // Refresh attempts
  const handleRefreshHistory = async () => {
    try {
      const newAttempts = await attemptService.getQuestionAttempts(questionId);
      setAttempts(newAttempts);
    } catch (err) {
      console.error('Failed to refresh history:', err);
    }
  };

  // Resizable panel handlers for left divider
  const updateLeftWidthFromPointer = (clientX: number) => {
    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = clientX - rect.left;
    const nextPercent = (x / rect.width) * 100;
    const clamped = Math.min(40, Math.max(20, nextPercent));
    setLeftPercent(clamped);
  };

  // Resizable panel handlers for right divider
  const updateCenterWidthFromPointer = (clientX: number) => {
    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = clientX - rect.left;
    const totalLeftAndCenter = (x / rect.width) * 100;
    const nextCenterPercent = totalLeftAndCenter - leftPercent;
    const clamped = Math.min(50, Math.max(25, nextCenterPercent));
    setCenterPercent(clamped);
  };

  // Loading state
  if (loading) {
    return (
      <div className="loading-center" style={{ minHeight: '50vh' }}>
        <div className="spinner" />
        <span>Loading question…</span>
      </div>
    );
  }

  // Error state
  if (error || !question) {
    return (
      <div style={{ padding: 24, display: 'grid', gap: 16, maxWidth: 600 }}>
        <div className="da-alert alert-error" role="alert">
          <strong>Error</strong>
          <span>{error || 'Question not found'}</span>
        </div>
        <div>
          <button className="btn btn-secondary" onClick={() => router.push(backUrl ?? '/student')}>
            Back
          </button>
        </div>
      </div>
    );
  }

  const rightPercent = 100 - leftPercent - centerPercent;

  return (
    <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 12, height: 'calc(100vh - 60px)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10 }}>
        <div style={{ marginRight: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          <AssessmentTimer />
          <QuestionWeightBadge weight={weight} />
        </div>
        <button
          className="btn btn-brand"
          style={{ minHeight: 34, padding: '0 12px', fontSize: 13 }}
          onClick={() => router.push(backUrl ?? '/student')}
        >
          <IconLogout />
          Save and Exit
        </button>
      </div>

      <QuestionNavigator />

      {/* 3-Panel Layout */}
      <Box
        ref={containerRef}
        style={{
          display: 'flex',
          gap: 0,
          alignItems: 'stretch',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          width: '100%',
          flex: 1,
          minHeight: 0,
        }}
      >
          {/* Left Panel - Question Details */}
          <Box
            style={{
              flex: `0 0 ${leftPercent}%`,
              minWidth: 250,
              background: 'var(--surface)',
              overflow: 'hidden',
            }}
          >
            <QuestionPanel question={question} />
          </Box>

          {/* Left Divider */}
          <Box
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              setIsDraggingLeft(true);
              updateLeftWidthFromPointer(event.clientX);
            }}
            onPointerMove={(event) => {
              if (!isDraggingLeft) return;
              updateLeftWidthFromPointer(event.clientX);
            }}
            onPointerUp={(event) => {
              event.currentTarget.releasePointerCapture(event.pointerId);
              setIsDraggingLeft(false);
            }}
            style={{
              width: 8,
              cursor: 'col-resize',
              background: 'var(--border)',
              position: 'relative',
              flex: '0 0 8px',
              userSelect: 'none',
              touchAction: 'none',
            }}
          >
            <Box
              style={{
                position: 'absolute',
                top: '25%',
                bottom: '25%',
                left: '50%',
                width: 3,
                transform: 'translateX(-50%)',
                background: 'var(--border-strong)',
                borderRadius: 2,
              }}
            />
          </Box>

          {/* Center Panel - Editor */}
          <Box
            style={{
              flex: `0 0 ${centerPercent}%`,
              minWidth: 300,
              background: 'var(--surface)',
              overflow: 'hidden',
            }}
          >
            <EditorPanel
              query={query}
              onQueryChange={setQuery}
              onExecute={handleExecute}
              onClear={handleClear}
              isExecuting={isExecuting}
              executionTime={result?.execution_time_ms || null}
              isCoolingDown={isCoolingDown}
              limitReached={limitReached}
              maxQueries={maxQueries}
              attemptsUsed={attemptsUsed}
              isBagheeraActive={isBagheeraActive}
            />
          </Box>

          {/* Right Divider */}
          <Box
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              setIsDraggingRight(true);
              updateCenterWidthFromPointer(event.clientX);
            }}
            onPointerMove={(event) => {
              if (!isDraggingRight) return;
              updateCenterWidthFromPointer(event.clientX);
            }}
            onPointerUp={(event) => {
              event.currentTarget.releasePointerCapture(event.pointerId);
              setIsDraggingRight(false);
            }}
            style={{
              width: 8,
              cursor: 'col-resize',
              background: 'var(--border)',
              position: 'relative',
              flex: '0 0 8px',
              userSelect: 'none',
              touchAction: 'none',
            }}
          >
            <Box
              style={{
                position: 'absolute',
                top: '25%',
                bottom: '25%',
                left: '50%',
                width: 3,
                transform: 'translateX(-50%)',
                background: 'var(--border-strong)',
                borderRadius: 2,
              }}
            />
          </Box>

          {/* Right Panel - Results */}
          <Box
            style={{
              flex: `0 0 ${rightPercent}%`,
              minWidth: 250,
              background: 'var(--surface)',
              overflow: 'hidden',
            }}
          >
            <ResultsPanel
              result={result}
              attempts={attempts}
              onRefreshHistory={handleRefreshHistory}
              questionId={questionId}
              question={question}
              currentQuery={query}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          </Box>
        </Box>
    </div>
  );
}
