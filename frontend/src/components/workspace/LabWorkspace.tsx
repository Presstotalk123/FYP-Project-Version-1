'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ActionIcon,
  Box,
  Container,
  Group,
  Loader,
  Stack,
  Text,
  Title,
  Alert,
  Button,
} from '@mantine/core';
import { IconArrowLeft, IconAlertCircle, IconLogout, IconRefresh, IconInfoCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { modals } from '@mantine/modals';
import { LabDetail, LabExecuteResponse, LabAttemptResponse, LabQueryHistoryResponse, DatabaseState, LabTask, LabTaskCreate, LabTaskAssignAnswer, LabTaskProgress } from '@/types/lab.types';
import { labService } from '@/services/lab.service';
import { LabDescriptionPanel } from './LabDescriptionPanel';
import { LabEditorPanel } from './LabEditorPanel';
import { LabResultsPanel } from './LabResultsPanel';

interface LabWorkspaceProps {
  labId: number;
  isStaffMode?: boolean;
  reviewMode?: boolean;
  reviewStudentId?: number;
}

export function LabWorkspace({
  labId,
  isStaffMode = false,
  reviewMode = false,
  reviewStudentId,
}: LabWorkspaceProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement | null>(null);

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

        // Check if lab is running (students only - staff can access any lab for testing)
        if (!isStaffMode && !labData.is_running) {
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
        const progressData = await labService.getLabTaskProgress(labId, controller.signal);
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
  }, [labId]);

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
    try {
      const response = await labService.executeQuery(sessionId, query, reviewMode);
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
    try {
      const response = await labService.executeQuery(sessionId, queryText, reviewMode);
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
      await labService.exitSession(labId);
      notifications.show({
        title: 'Session Ended',
        message: 'Your lab session has been terminated',
        color: 'blue',
      });
      router.push(isStaffMode ? '/admin/labs' : '/student/labs');
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

      notifications.show({
        title: response.is_correct ? 'Correct!' : 'Incorrect',
        message: response.message,
        color: response.is_correct ? 'green' : 'red',
      });

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
      <Container fluid px="sm" py="md">
        <Stack align="center" justify="center" style={{ height: '50vh' }}>
          <Loader size="lg" />
          <Text c="dimmed">Loading lab...</Text>
        </Stack>
      </Container>
    );
  }

  // Error state
  if (error || !lab) {
    return (
      <Container fluid px="sm" py="md">
        <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
          {error || 'Lab not found'}
        </Alert>
        <Button mt="md" variant="light" onClick={() => router.push(isStaffMode ? '/admin/labs' : '/student/labs')}>
          Back to Labs
        </Button>
      </Container>
    );
  }

  const rightPercent = 100 - leftPercent - centerPercent;

  return (
    <Container fluid px="sm" py="md">
      <Stack gap="md">
        {/* Header */}
        <Group justify="space-between" align="center">
          <Group align="baseline" gap="sm">
            <ActionIcon
              onClick={() => router.push(isStaffMode ? '/admin/labs' : '/student/labs')}
              variant="subtle"
              size="sm"
              aria-label="Back to labs"
            >
              <IconArrowLeft size={18} />
            </ActionIcon>
            <Title order={2}>Lab Workspace</Title>
          </Group>
          <Group gap="sm">
            <Button
              leftSection={<IconRefresh size={16} />}
              color="orange"
              variant="light"
              onClick={handleReset}
              loading={isResetting}
              size="sm"
            >
              Reset Database
            </Button>
            <Button
              leftSection={<IconLogout size={16} />}
              color="red"
              variant="light"
              onClick={handleExit}
              size="sm"
            >
              Exit Lab
            </Button>
          </Group>
        </Group>

        {/* Staff Testing Mode Banner */}
        {isStaffMode && !reviewMode && (
          <Alert
            icon={<IconInfoCircle size={16} />}
            color="cyan"
            variant="light"
            title="Staff Testing Mode"
          >
            You are testing this lab as staff. Your session is independent from student sessions.
          </Alert>
        )}

        {/* Review Mode Banner */}
        {reviewMode && (
          <Alert
            icon={<IconInfoCircle size={16} />}
            color="violet"
            variant="light"
            title={`Reviewing Student Activity: ${studentEmail}`}
          >
            You are reviewing this student&apos;s query history. Use &quot;Execute Next&quot; in the Student Queries tab to step through their queries sequentially. Each query builds on the previous ones to recreate the student&apos;s database progression.
          </Alert>
        )}

        {/* 3-Panel Layout */}
        <Box
          ref={containerRef}
          style={{
            display: 'flex',
            gap: 0,
            alignItems: 'stretch',
            border: '1px solid var(--mantine-color-gray-3)',
            borderRadius: 12,
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
              background: 'var(--mantine-color-body)',
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
              background: 'var(--mantine-color-gray-2)',
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
                background: 'var(--mantine-color-gray-6)',
                borderRadius: 2,
              }}
            />
          </Box>

          {/* Center Panel - Editor */}
          <Box
            style={{
              flex: `0 0 ${centerPercent}%`,
              minWidth: 300,
              background: 'var(--mantine-color-body)',
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
              background: 'var(--mantine-color-gray-2)',
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
                background: 'var(--mantine-color-gray-6)',
                borderRadius: 2,
              }}
            />
          </Box>

          {/* Right Panel - Results */}
          <Box
            style={{
              flex: `0 0 ${rightPercent}%`,
              minWidth: 250,
              background: 'var(--mantine-color-body)',
              overflow: 'hidden',
            }}
          >
            <LabResultsPanel
              result={result}
              attempts={attempts}
              databaseState={databaseState}
              isLoadingDatabase={isLoadingDatabase}
              isStaffMode={isStaffMode}
              tasks={tasks}
              currentQuery={query}
              taskProgress={taskProgress}
              onAssignToTask={handleAssignTaskAnswer}
              onSubmitToTask={handleSubmitToTask}
              reviewMode={reviewMode}
              onRerunQuery={handleRerunQuery}
              isExecuting={isExecuting}
              onCopyQuery={handleCopyQuery}
            />
          </Box>
        </Box>
      </Stack>
    </Container>
  );
}
