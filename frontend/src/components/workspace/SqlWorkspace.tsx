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
} from '@mantine/core';
import { IconArrowLeft, IconAlertCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { QuestionDetail } from '@/types/question.types';
import { ExecuteResponse, Attempt } from '@/types/attempt.types';
import { questionService } from '@/services/question.service';
import { executeService } from '@/services/execute.service';
import { attemptService } from '@/services/attempt.service';
import { QuestionPanel } from './QuestionPanel';
import { EditorPanel } from './EditorPanel';
import { ResultsPanel } from './ResultsPanel';

interface SqlWorkspaceProps {
  questionId: number;
}

export function SqlWorkspace({ questionId }: SqlWorkspaceProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement | null>(null);

  // State
  const [question, setQuestion] = useState<QuestionDetail | null>(null);
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Resizable panel state
  const [leftPercent, setLeftPercent] = useState(30);
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [centerPercent, setCenterPercent] = useState(40);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

  // Fetch question and attempts on mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [questionData, attemptsData] = await Promise.all([
          questionService.getQuestionById(questionId),
          attemptService.getQuestionAttempts(questionId),
        ]);
        setQuestion(questionData);
        setAttempts(attemptsData);
      } catch (err) {
        const error = err as { response?: { data?: { detail?: string } } };
        setError(error.response?.data?.detail || 'Failed to load question');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [questionId]);

  // Execute query
  const handleExecute = async () => {
    if (!query.trim()) {
      notifications.show({
        title: 'Empty Query',
        message: 'Please enter a SQL query',
        color: 'yellow',
      });
      return;
    }

    setIsExecuting(true);
    try {
      const response = await executeService.executeQuery({
        question_id: questionId,
        query,
      });
      setResult(response);

      if (response.is_correct) {
        notifications.show({
          title: 'Correct!',
          message: 'Your query returned the expected results',
          color: 'green',
        });
      }

      // Refresh attempts
      const newAttempts = await attemptService.getQuestionAttempts(questionId);
      setAttempts(newAttempts);
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
      <Container fluid px="sm" py="md">
        <Stack align="center" justify="center" style={{ height: '50vh' }}>
          <Loader size="lg" />
          <Text c="dimmed">Loading question...</Text>
        </Stack>
      </Container>
    );
  }

  // Error state
  if (error || !question) {
    return (
      <Container fluid px="sm" py="md">
        <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
          {error || 'Question not found'}
        </Alert>
      </Container>
    );
  }

  const rightPercent = 100 - leftPercent - centerPercent;

  return (
    <Container fluid px="sm" py="md">
      <Stack gap="md">
        {/* Header */}
        <Group align="baseline" gap="sm">
          <ActionIcon
            onClick={() => router.push('/student')}
            variant="subtle"
            size="sm"
            aria-label="Back to dashboard"
          >
            <IconArrowLeft size={18} />
          </ActionIcon>
          <Title order={2}>SQL Workspace</Title>
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
          {/* Left Panel - Question Details */}
          <Box
            style={{
              flex: `0 0 ${leftPercent}%`,
              minWidth: 250,
              background: 'var(--mantine-color-body)',
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
            <EditorPanel
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
            <ResultsPanel
              result={result}
              attempts={attempts}
              onRefreshHistory={handleRefreshHistory}
            />
          </Box>
        </Box>
      </Stack>
    </Container>
  );
}
