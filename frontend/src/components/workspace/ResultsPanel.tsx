'use client';

import {
  Alert,
  Badge,
  Card,
  Code,
  Group,
  ScrollArea,
  Stack,
  Table,
  Tabs,
  Text,
} from '@mantine/core';
import { IconCheck, IconX } from '@tabler/icons-react';
import { ExecuteResponse, Attempt } from '@/types/attempt.types';
import { QuestionDetail } from '@/types/question.types';
import { ChatTab } from './ChatTab';

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
  return (
    <Tabs defaultValue="results" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Tabs.List>
        <Tabs.Tab value="results">Results</Tabs.Tab>
        <Tabs.Tab value="history">History</Tabs.Tab>
        <Tabs.Tab value="chat">AI Tutor</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="results" style={{ flex: 1, overflow: 'auto' }} p="md">
        {!result ? (
          <Text c="dimmed" ta="center" mt="xl">
            Run a query to see results
          </Text>
        ) : result.error_message ? (
          <Alert icon={<IconX size={16} />} color="red" title="Error">
            {result.error_message}
          </Alert>
        ) : (
          <Stack gap="md">
            <Alert
              icon={result.is_correct ? <IconCheck size={16} /> : <IconX size={16} />}
              color={result.is_correct ? 'green' : 'red'}
              title={result.is_correct ? 'Correct!' : 'Incorrect'}
            >
              {result.is_correct
                ? 'Your query returned the expected results.'
                : 'Your query results don\'t match the expected output.'}
            </Alert>

            <div>
              <Text size="sm" fw={500} mb="xs">
                Query Results
              </Text>
              <ScrollArea>
                <Table striped highlightOnHover withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      {result.columns.map((col) => (
                        <Table.Th key={col}>{col}</Table.Th>
                      ))}
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {result.results.map((row, idx) => (
                      <Table.Tr key={idx}>
                        {result.columns.map((col) => (
                          <Table.Td key={col}>
                            {row[col] !== null && row[col] !== undefined ? String(row[col]) : 'NULL'}
                          </Table.Td>
                        ))}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
              <Text size="xs" c="dimmed" mt="xs">
                {result.row_count} {result.row_count === 1 ? 'row' : 'rows'} returned
              </Text>
            </div>
          </Stack>
        )}
      </Tabs.Panel>

      <Tabs.Panel value="history" style={{ flex: 1, overflow: 'auto' }} p="md">
        {attempts.length === 0 ? (
          <Text c="dimmed" ta="center" mt="xl">
            No attempts yet for this question
          </Text>
        ) : (
          <Stack gap="sm">
            {attempts.map((attempt) => (
              <Card key={attempt.id} withBorder padding="sm">
                <Stack gap="xs">
                  <Group justify="space-between">
                    <Badge color={attempt.is_correct ? 'green' : 'red'} variant="light">
                      {attempt.is_correct ? 'Correct' : 'Incorrect'}
                    </Badge>
                    <Text size="xs" c="dimmed">
                      {new Date(attempt.submitted_at).toLocaleString()}
                    </Text>
                  </Group>
                  <Code
                    style={{
                      fontSize: '11px',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                    }}
                  >
                    {attempt.query.length > 100
                      ? attempt.query.substring(0, 100) + '...'
                      : attempt.query}
                  </Code>
                  {attempt.execution_time_ms && (
                    <Text size="xs" c="dimmed">
                      Execution time: {attempt.execution_time_ms.toFixed(2)}ms
                    </Text>
                  )}
                </Stack>
              </Card>
            ))}
          </Stack>
        )}
      </Tabs.Panel>

      <Tabs.Panel value="chat" style={{ flex: 1, overflow: 'auto' }}>
        <ChatTab
          questionId={questionId}
          question={question}
          currentQuery={currentQuery}
          result={result}
        />
      </Tabs.Panel>
    </Tabs>
  );
}
