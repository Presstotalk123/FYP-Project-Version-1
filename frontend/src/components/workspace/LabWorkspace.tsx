'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Box,
  Text,
} from '@mantine/core';

/* ── SVG icons ── */
const IconLogout = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
  </svg>
);
const IconRefresh = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
  </svg>
);
const IconInfoCircle = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>
);
const IconAlertCircle = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>
);
import { notifications } from '@mantine/notifications';
import { modals } from '@mantine/modals';
import { LabDetail, LabExecuteResponse, LabQueryHistoryResponse, DatabaseState, LabTask, LabTaskCreate, LabTaskProgress, DB_RESET_SENTINEL } from '@/types/lab.types';
import { labService } from '@/services/lab.service';
import { chatbotService, LabQueryReviewResponse } from '@/services/chatbot.service';
import { LabDescriptionPanel } from './LabDescriptionPanel';
import { LabEditorPanel } from './LabEditorPanel';
import { LabResultsPanel } from './LabResultsPanel';
import { AssessmentTimer } from '@/components/assessment/AssessmentTimer';
import { useAssessmentTimer } from '@/contexts/AssessmentTimerContext';

interface LabWorkspaceProps {
  labId: number;
  isStaffMode?: boolean;
  reviewMode?: boolean;
  reviewStudentId?: number;
  backUrl?: string;
  inAssessment?: boolean;
}

export function LabWorkspace({
  labId,
  isStaffMode = false,
  reviewMode = false,
  reviewStudentId,
  backUrl,
  inAssessment = false,
}: LabWorkspaceProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const taskOrderChanged = useRef(false);
  const timer = useAssessmentTimer();

  // State
  const [lab, setLab] = useState<LabDetail | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<LabExecuteResponse | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<LabQueryHistoryResponse[]>([]);
  const [isResetting, setIsResetting] = useState(false);
  const [databaseState, setDatabaseState] = useState<DatabaseState | null>(null);
  const [isLoadingDatabase, setIsLoadingDatabase] = useState(false);

  // Task state
  const [tasks, setTasks] = useState<LabTask[]>([]);
  const [isLoadingTasks, setIsLoadingTasks] = useState(false);
  const [taskProgress, setTaskProgress] = useState<Record<number, LabTaskProgress>>({});

  // Review mode state
  const [studentQueries, setStudentQueries] = useState<LabQueryHistoryResponse[]>([]);
  const [currentQueryIndex, setCurrentQueryIndex] = useState<number>(0);
  const [executedIndices, setExecutedIndices] = useState<Set<number>>(new Set());
  const [isLoadingStudentHistory, setIsLoadingStudentHistory] = useState(false);
  const [studentEmail, setStudentEmail] = useState<string>('');

  // AI Query Review state
  const [labReviewData, setLabReviewData] = useState<LabQueryReviewResponse | null>(null);
  const [isLabReviewing, setIsLabReviewing] = useState(false);

  // Resizable panel state
  const [leftPercent, setLeftPercent] = useState(30);
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [centerPercent, setCenterPercent] = useState(40);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

  // Initialize lab and session on mount
  useEffect(() => {
    const controller = new AbortController();

    const initializeLab = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch lab details
        const labData = await labService.getLabById(labId, controller.signal);
        if (controller.signal.aborted) return;
        setLab(labData);

        // Check if lab is running (students only - staff and assessment context bypass this)
        if (!isStaffMode && !inAssessment && !labData.is_running) {
          setError('This lab is not currently running');
          return;
        }

        // Start or get existing session
        const sessionData = await labService.startSession(labId, controller.signal);
        if (controller.signal.aborted) return;
        setSessionId(sessionData.session_id);

        // Fetch comprehensive query history (all sessions)
        const attemptsData = await labService.getLabHistory(labId, controller.signal);
        if (controller.signal.aborted) return;
        setAttempts(attemptsData);

        // Fetch database state
        setIsLoadingDatabase(true);
        try {
          const dbState = await labService.getDatabaseState(sessionData.session_id, controller.signal);
          if (controller.signal.aborted) return;
          setDatabaseState(dbState);
        } catch (err) {
          if ((err as any).name === 'AbortError' || (err as any).name === 'CanceledError') return;
          console.error('Failed to fetch database state:', err);
        } finally {
          if (!controller.signal.aborted) {
            setIsLoadingDatabase(false);
          }
        }

        if (controller.signal.aborted) return;
        notifications.show({
          title: 'Session Started',
          message: 'Your lab session is ready!',
          color: 'green',
        });
      } catch (err) {
        if ((err as any).name === 'AbortError' || (err as any).name === 'CanceledError') return;
        const error = err as { response?: { data?: { detail?: string } } };
        setError(error.response?.data?.detail || 'Failed to initialize lab');
        notifications.show({
          title: 'Error',
          message: error.response?.data?.detail || 'Failed to initialize lab',
          color: 'red',
        });
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    initializeLab();
    return () => controller.abort();
  }, [labId]);

  // Fetch tasks on mount
  useEffect(() => {
    const controller = new AbortController();

    const fetchTasks = async () => {
      if (!labId) return;

      setIsLoadingTasks(true);
      try {
        const tasksData = await labService.getLabTasks(labId, controller.signal);
        if (controller.signal.aborted) return;
        setTasks(tasksData);
      } catch (err) {
        if ((err as any).name === 'AbortError' || (err as any).name === 'CanceledError') return;
        console.error('Failed to fetch tasks:', err);
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingTasks(false);
        }
      }
    };

    fetchTasks();
    return () => controller.abort();
  }, [labId]);

  // Fetch task progress on mount
  useEffect(() => {
    const controller = new AbortController();

    const fetchProgress = async () => {
      if (!labId) return;

      try {
        const progressData = await labService.getLabTaskProgress(
          labId,
          controller.signal,
          reviewMode ? reviewStudentId : undefined
        );
        if (controller.signal.aborted) return;
        const progressMap = Object.fromEntries(
          progressData.tasks.map(p => [p.task_id, p])
        );
        setTaskProgress(progressMap);
      } catch (err) {
        if ((err as any).name === 'AbortError' || (err as any).name === 'CanceledError') return;
        console.error('Failed to fetch task progress:', err);
      }
    };

    fetchProgress();
    return () => controller.abort();
  }, [labId, reviewMode, reviewStudentId]);

  // Fetch student query history in review mode
  useEffect(() => {
    const controller = new AbortController();

    const fetchStudentHistory = async () => {
      if (!reviewMode || !reviewStudentId) return;

      setIsLoadingStudentHistory(true);
      try {
        const history = await labService.getStudentQueryHistory(labId, reviewStudentId, controller.signal);
        if (controller.signal.aborted) return;
        setStudentQueries(history);

        // Extract student email from first query if available
        if (history.length > 0 && history[0].student_email) {
          setStudentEmail(history[0].student_email);
        } else if (history.length > 0) {
          setStudentEmail(`Student ID: ${reviewStudentId}`);
        } else {
          setStudentEmail(`Student ID: ${reviewStudentId} (No queries)`);
        }
      } catch (err) {
        if ((err as any).name === 'AbortError' || (err as any).name === 'CanceledError') return;
        console.error('Failed to fetch student query history:', err);
        notifications.show({
          title: 'Error',
          message: 'Failed to load student query history',
          color: 'red',
        });
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingStudentHistory(false);
        }
      }
    };

    fetchStudentHistory();
    return () => controller.abort();
  }, [reviewMode, reviewStudentId, labId]);

  // Execute query
  const handleExecute = async () => {
    if (!sessionId || !query.trim()) {
      notifications.show({
        title: 'Empty Query',
        message: 'Please enter a SQL query',
        color: 'yellow',
      });
      return;
    }

    setIsExecuting(true);
    // Pause the assessment countdown while the query runs; the backend credits this time.
    timer.pause();
    let creditedEndTime: string | null | undefined;
    try {
      const response = await labService.executeQuery(sessionId, query, reviewMode);
      creditedEndTime = response.assessment_end_time;
      setResult(response);

      // Refresh comprehensive query history
      const attemptsData = await labService.getLabHistory(labId);
      setAttempts(attemptsData);

      // Refresh database state
      setIsLoadingDatabase(true);
      try {
        const dbState = await labService.getDatabaseState(sessionId);
        setDatabaseState(dbState);
      } catch (err) {
        console.error('Failed to refresh database state:', err);
      } finally {
        setIsLoadingDatabase(false);
      }

      if (response.success) {
        notifications.show({
          title: 'Success',
          message: `Query executed in ${response.execution_time_ms.toFixed(2)}ms`,
          color: 'green',
        });
      } else {
        notifications.show({
          title: 'Query Failed',
          message: response.error_message || 'Query execution failed',
          color: 'red',
        });
      }
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Execution Error',
        message: error.response?.data?.detail || 'Failed to execute query',
        color: 'red',
      });
    } finally {
      setIsExecuting(false);
      timer.resume(creditedEndTime);
    }
  };

  // Clear query
  const handleClear = () => {
    setQuery('');
  };

  // Rerun query from history
  const handleRerunQuery = async (queryText: string) => {
    // Set the query in the editor
    setQuery(queryText);

    // Wait briefly for the state to update and editor to render
    await new Promise((resolve) => setTimeout(resolve, 50));

    // Validate session
    if (!sessionId) {
      notifications.show({
        title: 'No Active Session',
        message: 'Cannot execute query without an active session',
        color: 'red',
      });
      return;
    }

    // Execute the query
    setIsExecuting(true);
    // Pause the assessment countdown while the query runs; the backend credits this time.
    timer.pause();
    let creditedEndTime: string | null | undefined;
    try {
      const response = await labService.executeQuery(sessionId, queryText, reviewMode);
      creditedEndTime = response.assessment_end_time;
      setResult(response);

      // Refresh query history
      const attemptsData = await labService.getLabHistory(labId);
      setAttempts(attemptsData);

      // Refresh database state
      setIsLoadingDatabase(true);
      try {
        const dbState = await labService.getDatabaseState(sessionId);
        setDatabaseState(dbState);
      } catch (err) {
        console.error('Failed to refresh database state:', err);
      } finally {
        setIsLoadingDatabase(false);
      }

      // Show success/failure notification
      if (response.success) {
        notifications.show({
          title: 'Query Re-executed',
          message: `Query executed in ${response.execution_time_ms.toFixed(2)}ms`,
          color: 'green',
        });
      } else {
        notifications.show({
          title: 'Query Failed',
          message: response.error_message || 'Query execution failed',
          color: 'red',
        });
      }
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Execution Error',
        message: error.response?.data?.detail || 'Failed to execute query',
        color: 'red',
      });
    } finally {
      setIsExecuting(false);
      timer.resume(creditedEndTime);
    }
  };

  // Copy query from history to editor (without executing)
  const handleCopyQuery = (queryText: string) => {
    setQuery(queryText);
  };

  // Execute next query in review mode
  const handleExecuteNext = async () => {
    if (!reviewMode || currentQueryIndex >= studentQueries.length || !sessionId) return;

    const nextQuery = studentQueries[currentQueryIndex];

    // If this entry is a DB reset sentinel, replay the reset instead of executing SQL
    if (nextQuery.query === DB_RESET_SENTINEL) {
      const resetIndex = currentQueryIndex;
      setExecutedIndices((prev) => new Set([...prev, resetIndex]));
      setCurrentQueryIndex((prev) => prev + 1);

      setIsResetting(true);
      try {
        await labService.resetSession(labId);

        // Refresh database state to reflect the reset
        setIsLoadingDatabase(true);
        try {
          const dbState = await labService.getDatabaseState(sessionId);
          setDatabaseState(dbState);
        } catch (err) {
          console.error('Failed to refresh database state after review reset:', err);
        } finally {
          setIsLoadingDatabase(false);
        }

        notifications.show({
          title: 'Database Reset Replayed',
          message: 'The student reset their database at this point. Your database has been reset to match.',
          color: 'orange',
        });
      } catch (err) {
        const error = err as { response?: { data?: { detail?: string } } };
        notifications.show({
          title: 'Reset Failed',
          message: error.response?.data?.detail || 'Failed to replay database reset',
          color: 'red',
        });
      } finally {
        setIsResetting(false);
      }
      return;
    }

    setQuery(nextQuery.query);

    // Wait a brief moment for the query to be set in the editor
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Execute the query
    await handleExecute();

    // Mark as executed
    setExecutedIndices((prev) => new Set([...prev, currentQueryIndex]));

    // Move to next query
    setCurrentQueryIndex((prev) => prev + 1);
  };

  // Select a specific query for viewing (not execution)
  const handleSelectQuery = (index: number) => {
    if (!reviewMode) return;

    setCurrentQueryIndex(index);
    setQuery(studentQueries[index].query);

    notifications.show({
      title: 'Query Loaded',
      message: 'Query loaded into editor. Use "Execute Next" to run it sequentially.',
      color: 'blue',
    });
  };

  // Reset database
  const handleReset = () => {
    modals.openConfirmModal({
      title: 'Reset Database',
      children: (
        <Text size="sm">
          Are you sure you want to reset your database? This will delete all your changes and restore the original template. This action cannot be undone.
        </Text>
      ),
      labels: { confirm: 'Reset', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        setIsResetting(true);
        try {
          await labService.resetSession(labId);

          // Refresh comprehensive query history after reset
          if (sessionId) {
            const attemptsData = await labService.getLabHistory(labId);
            setAttempts(attemptsData);

            // Refresh database state
            try {
              const dbState = await labService.getDatabaseState(sessionId);
              setDatabaseState(dbState);
            } catch (err) {
              console.error('Failed to refresh database state after reset:', err);
            }

            // Refresh task progress after reset to clear completion status
            try {
              const progressData = await labService.getLabTaskProgress(labId);
              const progressMap = Object.fromEntries(
                progressData.tasks.map(p => [p.task_id, p])
              );
              setTaskProgress(progressMap);
            } catch (err) {
              console.error('Failed to refresh task progress after reset:', err);
            }
          }

          // Clear current results
          setResult(null);
          setQuery('');

          notifications.show({
            title: 'Database Reset',
            message: 'Your database has been reset to the original template',
            color: 'green',
          });
        } catch (err) {
          const error = err as { response?: { data?: { detail?: string } } };
          notifications.show({
            title: 'Reset Failed',
            message: error.response?.data?.detail || 'Failed to reset database',
            color: 'red',
          });
        } finally {
          setIsResetting(false);
        }
      },
    });
  };

  // Exit session
  const handleExit = async () => {
    try {
      if (isStaffMode && taskOrderChanged.current) {
        await Promise.all(
          tasks.map(task =>
            labService.updateLabTask(labId, task.id, { order_index: task.order_index })
          )
        );
      }
      await labService.exitSession(labId);
      notifications.show({
        title: 'Session Ended',
        message: 'Your lab session has been terminated',
        color: 'blue',
      });
      router.push(isStaffMode ? '/admin/labs' : (backUrl ?? '/student/labs'));
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to exit session',
        color: 'red',
      });
    }
  };

  // Task management handlers
  const handleCreateTask = async (taskData: LabTaskCreate) => {
    try {
      const newTask = await labService.createLabTask(labId, taskData);
      setTasks(prev => [...prev, newTask].sort((a, b) => a.order_index - b.order_index));
      notifications.show({
        title: 'Task Created',
        message: 'Lab task created successfully',
        color: 'green',
      });
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to create task',
        color: 'red',
      });
    }
  };

  const handleDeleteTask = async (taskId: number) => {
    try {
      await labService.deleteLabTask(labId, taskId);
      setTasks(prev => prev.filter(t => t.id !== taskId));
      notifications.show({
        title: 'Task Deleted',
        message: 'Task deleted successfully',
        color: 'green',
      });
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to delete task',
        color: 'red',
      });
    }
  };

  const handleUpdateTask = async (taskId: number, data: { title: string; description: string }) => {
    try {
      const updatedTask = await labService.updateLabTask(labId, taskId, data);
      setTasks(prev => prev.map(t => t.id === taskId ? updatedTask : t));
      notifications.show({
        title: 'Task Updated',
        message: 'Task updated successfully',
        color: 'green',
      });
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to update task',
        color: 'red',
      });
    }
  };

  const handleReorderTasks = (reorderedTasks: LabTask[]) => {
    const tasksWithNewOrder = reorderedTasks.map((task, index) => ({
      ...task,
      order_index: index,
    }));
    setTasks(tasksWithNewOrder);
    taskOrderChanged.current = true;
  };

  const handleAssignTaskAnswer = async (taskId: number, query: string) => {
    try {
      const updatedTask = await labService.assignTaskAnswer(labId, taskId, { query });
      setTasks(prev => prev.map(t => t.id === taskId ? updatedTask : t));
      notifications.show({
        title: 'Answer Assigned',
        message: 'Query result assigned as correct answer',
        color: 'green',
      });
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to assign answer',
        color: 'red',
      });
    }
  };

  const handleSubmitToTask = async (taskId: number) => {
    if (!result || !sessionId || !query.trim()) return;

    // Clear any previous review when a new submission starts
    setLabReviewData(null);

    try {
      const response = await labService.submitTaskAnswer({
        task_id: taskId,
        session_id: sessionId,
        columns: result.columns,
        results: result.results,
        query: query,
        execution_time_ms: result.execution_time_ms,
        row_count: result.row_count,
      });

      if (response.is_correct === null) {
        notifications.show({
          title: 'Submitted',
          message: response.message,
          color: 'blue',
        });
      } else {
        notifications.show({
          title: response.is_correct ? 'Correct!' : 'Incorrect',
          message: response.message,
          color: response.is_correct ? 'green' : 'red',
        });
      }

      // Trigger AI review in background for wrong submissions
      // (skip when is_correct is null - the lab hides correctness from students -
      // or when this lab has AI assist turned off independent of correctness)
      if (response.is_correct === false && !lab?.disable_ai_assist) {
        setIsLabReviewing(true);
        chatbotService
          .reviewLabQuery(labId, sessionId, taskId, query)
          .then(setLabReviewData)
          .catch(() => {}) // fail silently
          .finally(() => setIsLabReviewing(false));
      }

      // Refresh progress
      const progressData = await labService.getLabTaskProgress(labId);
      const progressMap = Object.fromEntries(
        progressData.tasks.map(p => [p.task_id, p])
      );
      setTaskProgress(progressMap);
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Submission Failed',
        message: error.response?.data?.detail || 'Failed to submit answer',
        color: 'red',
      });
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
        <span>Loading lab…</span>
      </div>
    );
  }

  // Error state
  if (error || !lab) {
    return (
      <div style={{ padding: 24, display: 'grid', gap: 16, maxWidth: 600 }}>
        <div className="da-alert alert-error" role="alert">
          <strong>Error</strong>
          <span>{error || 'Lab not found'}</span>
        </div>
        <div>
          <button className="btn btn-secondary" onClick={() => router.push(isStaffMode ? '/admin/labs' : (backUrl ?? '/student/labs'))}>
            Back to Labs
          </button>
        </div>
      </div>
    );
  }

  const rightPercent = 100 - leftPercent - centerPercent;

  return (
    <div style={{ padding: '12px 16px', display: 'grid', gap: 12 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10 }}>
        {inAssessment && <div style={{ marginRight: 'auto' }}><AssessmentTimer /></div>}
        <button
          className="btn btn-secondary"
          style={{ minHeight: 34, padding: '0 12px', fontSize: 13 }}
          onClick={handleReset}
          disabled={isResetting}
        >
          <IconRefresh />
          {isResetting ? 'Resetting…' : 'Reset Database'}
        </button>
        <button
          className="btn btn-brand"
          style={{ minHeight: 34, padding: '0 12px', fontSize: 13 }}
          onClick={handleExit}
        >
          <IconLogout />
          Save and Exit
        </button>
      </div>

      {/* Review Mode Banner */}
      {reviewMode && (
        <div className="da-alert alert-info" role="alert">
          <strong style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <IconInfoCircle />
            Reviewing Student Activity: {studentEmail}
          </strong>
          <span>
            You are reviewing this student&apos;s query history. Use &quot;Execute Next&quot; in the Student Queries tab to step through their queries sequentially. Each query builds on the previous ones to recreate the student&apos;s database progression.
          </span>
        </div>
      )}

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
          height: '70vh',
        }}
      >
        {/* Left Panel - Lab Description */}
        <Box
          style={{
            flex: `0 0 ${leftPercent}%`,
            minWidth: 250,
            background: 'var(--surface)',
            overflow: 'hidden',
          }}
        >
            <LabDescriptionPanel
              lab={lab}
              sessionId={sessionId}
              isStaffMode={isStaffMode}
              tasks={tasks}
              isLoadingTasks={isLoadingTasks}
              taskProgress={taskProgress}
              onCreateTask={handleCreateTask}
              onDeleteTask={handleDeleteTask}
              onEditTask={handleUpdateTask}
              onReorderTasks={handleReorderTasks}
              reviewMode={reviewMode}
              studentQueries={studentQueries}
              currentQueryIndex={currentQueryIndex}
              executedIndices={executedIndices}
              onSelectQuery={handleSelectQuery}
              onExecuteNext={handleExecuteNext}
              isLoadingStudentHistory={isLoadingStudentHistory}
              studentEmail={studentEmail}
            />
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
          <LabEditorPanel
            query={query}
            onQueryChange={setQuery}
            onExecute={handleExecute}
            onClear={handleClear}
            isExecuting={isExecuting}
            executionTime={result?.execution_time_ms || null}
            labType={lab?.lab_type ?? 'sql'}
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
          <LabResultsPanel
            result={result}
            attempts={attempts}
            databaseState={databaseState}
            isLoadingDatabase={isLoadingDatabase}
            isStaffMode={isStaffMode}
            hideCorrectness={lab?.hide_correctness ?? false}
            disableAiAssist={lab?.disable_ai_assist ?? false}
            tasks={tasks}
            currentQuery={query}
            taskProgress={taskProgress}
            onAssignToTask={handleAssignTaskAnswer}
            onSubmitToTask={handleSubmitToTask}
            reviewMode={reviewMode}
            onRerunQuery={handleRerunQuery}
            isExecuting={isExecuting}
            onCopyQuery={handleCopyQuery}
            lastReviewData={labReviewData}
            isReviewing={isLabReviewing}
            labId={labId}
            sessionId={sessionId}
          />
        </Box>
      </Box>
    </div>
  );
}
