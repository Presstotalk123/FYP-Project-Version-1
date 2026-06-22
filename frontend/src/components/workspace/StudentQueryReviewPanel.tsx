'use client';

import {
  Stack,
  Button,
  Card,
  Text,
  Badge,
  Group,
  ScrollArea,
  Alert,
  Code,
  Loader,
} from '@mantine/core';
import {
  IconPlayerPlay,
  IconCheck,
  IconAlertCircle,
  IconInfoCircle,
} from '@tabler/icons-react';
import { LabQueryHistoryResponse } from '@/types/lab.types';

interface StudentQueryReviewPanelProps {
  queries: LabQueryHistoryResponse[];
  currentIndex: number;
  executedIndices: Set<number>;
  onSelectQuery: (index: number) => void;
  onExecuteNext: () => void;
  isLoading: boolean;
  studentEmail: string;
}

export function StudentQueryReviewPanel({
  queries,
  currentIndex,
  executedIndices,
  onSelectQuery,
  onExecuteNext,
  isLoading,
  studentEmail,
}: StudentQueryReviewPanelProps) {
  if (isLoading) {
    return (
      <Stack align="center" justify="center" p="md" style={{ minHeight: '200px' }}>
        <Loader size="sm" />
        <Text c="dimmed">Loading student query history...</Text>
      </Stack>
    );
  }

  if (queries.length === 0) {
    return (
      <Alert color="blue" icon={<IconAlertCircle size={16} />} m="md">
        This student has no query history for this lab.
      </Alert>
    );
  }

  const hasNextQuery = currentIndex < queries.length;

  return (
    <Stack gap="md" p="md" style={{ height: '100%' }}>
      {/* Header with Execute Next button */}
      <Card withBorder padding="md" style={{ backgroundColor: 'var(--mantine-color-violet-0)' }}>
        <Stack gap="sm">
          <Group justify="space-between">
            <Text fw={500}>Query History Review</Text>
            <Badge>{queries.length} queries total</Badge>
          </Group>
          <Button
            leftSection={<IconPlayerPlay size={16} />}
            onClick={onExecuteNext}
            disabled={!hasNextQuery}
            fullWidth
            color="violet"
          >
            Execute Next Query ({currentIndex + 1}/{queries.length})
          </Button>
          <Alert icon={<IconInfoCircle size={14} />} color="violet" p="xs">
            <Text size="xs">
              Queries are executed sequentially to recreate the student&apos;s database
              progression. Click a query to view it, or use &quot;Execute Next&quot; to
              step through chronologically.
            </Text>
          </Alert>
        </Stack>
      </Card>

      {/* Query List */}
      <ScrollArea style={{ flex: 1 }} type="auto">
        <Stack gap="sm">
          {queries.map((query, index) => {
            const isExecuted = executedIndices.has(index);
            const isCurrent = index === currentIndex;
            const isPending = index > currentIndex;

            return (
              <Card
                key={query.id}
                withBorder
                padding="sm"
                radius="md"
                style={{
                  cursor: 'pointer',
                  borderColor: isCurrent
                    ? 'var(--mantine-color-violet-6)'
                    : undefined,
                  borderWidth: isCurrent ? 2 : 1,
                  opacity: isPending ? 0.6 : 1,
                  transition: 'all 0.2s ease',
                }}
                onClick={() => onSelectQuery(index)}
              >
                <Stack gap="xs">
                  <Group justify="space-between" wrap="nowrap">
                    <Group gap="xs">
                      <Badge size="sm" variant="light" color="gray">
                        #{index + 1}
                      </Badge>
                      {isExecuted && (
                        <Badge
                          color="green"
                          size="sm"
                          leftSection={<IconCheck size={12} />}
                        >
                          Reviewed
                        </Badge>
                      )}
                      {isCurrent && !isExecuted && (
                        <Badge color="violet" size="sm">
                          Current
                        </Badge>
                      )}
                      {isPending && (
                        <Badge color="gray" size="sm" variant="outline">
                          Pending
                        </Badge>
                      )}
                    </Group>
                    <Badge color={query.success ? 'green' : 'red'} size="xs">
                      {query.success ? 'Success' : 'Failed'}
                    </Badge>
                  </Group>

                  <Text size="xs" c="dimmed">
                    {new Date(query.submitted_at).toLocaleString()}
                  </Text>

                  <Code
                    block
                    style={{
                      fontSize: '11px',
                      maxHeight: '100px',
                      overflow: 'auto',
                      fontFamily: 'monospace',
                    }}
                  >
                    {query.query.length > 200
                      ? `${query.query.substring(0, 200)}...`
                      : query.query}
                  </Code>

                  {!query.success && query.error_message && (
                    <Alert color="red" p="xs" style={{ fontSize: '11px' }}>
                      {query.error_message}
                    </Alert>
                  )}

                  {query.success && (
                    <Group gap="xs">
                      <Text size="xs" c="dimmed">
                        {query.row_count} rows
                      </Text>
                      <Text size="xs" c="dimmed">
                        •
                      </Text>
                      <Text size="xs" c="dimmed">
                        {query.execution_time_ms.toFixed(2)}ms
                      </Text>
                    </Group>
                  )}
                </Stack>
              </Card>
            );
          })}
        </Stack>
      </ScrollArea>
    </Stack>
  );
}
