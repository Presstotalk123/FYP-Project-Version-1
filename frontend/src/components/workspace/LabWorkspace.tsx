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
import { IconArrowLeft, IconAlertCircle, IconLogout, IconRefresh } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { modals } from '@mantine/modals';
import { LabDetail, LabExecuteResponse, LabAttemptResponse, DatabaseState } from '@/types/lab.types';
import { labService } from '@/services/lab.service';
import { LabDescriptionPanel } from './LabDescriptionPanel';
import { LabEditorPanel } from './LabEditorPanel';
import { LabResultsPanel } from './LabResultsPanel';

interface LabWorkspaceProps {
  labId: number;
}

export function LabWorkspace({ labId }: LabWorkspaceProps) {
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
  const [attempts, setAttempts] = useState<LabAttemptResponse[]>([]);
  const [isResetting, setIsResetting] = useState(false);
  const [databaseState, setDatabaseState] = useState<DatabaseState | null>(null);
  const [isLoadingDatabase, setIsLoadingDatabase] = useState(false);

  // Resizable panel state
  const [leftPercent, setLeftPercent] = useState(30);
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [centerPercent, setCenterPercent] = useState(40);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

  // Initialize lab and session on mount
  useEffect(() => {
    const initializeLab = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch lab details
        const labData = await labService.getLabById(labId);
        setLab(labData);

        // Check if lab is running
        if (!labData.is_running) {
          setError('This lab is not currently running');
          return;
        }

        // Start or get existing session
        const sessionData = await labService.startSession(labId);
        setSessionId(sessionData.session_id);

        // Fetch attempts history
        const attemptsData = await labService.getSessionAttempts(sessionData.session_id);
        setAttempts(attemptsData);

        // Fetch database state
        setIsLoadingDatabase(true);
        try {
          const dbState = await labService.getDatabaseState(sessionData.session_id);
          setDatabaseState(dbState);
        } catch (err) {
          console.error('Failed to fetch database state:', err);
        } finally {
          setIsLoadingDatabase(false);
        }

        notifications.show({
          title: 'Session Started',
          message: 'Your lab session is ready!',
          color: 'green',
        });
      } catch (err) {
        const error = err as { response?: { data?: { detail?: string } } };
        setError(error.response?.data?.detail || 'Failed to initialize lab');
        notifications.show({
          title: 'Error',
          message: error.response?.data?.detail || 'Failed to initialize lab',
          color: 'red',
        });
      } finally {
        setLoading(false);
      }
    };

    initializeLab();
  }, [labId]);

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
      const response = await labService.executeQuery(sessionId, query);
      setResult(response);

      // Refresh attempts history
      const attemptsData = await labService.getSessionAttempts(sessionId);
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

          // Refresh attempts history after reset
          if (sessionId) {
            const attemptsData = await labService.getSessionAttempts(sessionId);
            setAttempts(attemptsData);

            // Refresh database state
            try {
              const dbState = await labService.getDatabaseState(sessionId);
              setDatabaseState(dbState);
            } catch (err) {
              console.error('Failed to refresh database state after reset:', err);
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
      router.push('/student/labs');
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to exit session',
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
        <Button mt="md" variant="light" onClick={() => router.push('/student/labs')}>
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
              onClick={() => router.push('/student/labs')}
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
            />
          </Box>
        </Box>
      </Stack>
    </Container>
  );
}
