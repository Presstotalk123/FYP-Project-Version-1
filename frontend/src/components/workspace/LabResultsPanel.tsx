'use client';

import { useState } from 'react';
import { Stack, Group, Text, Badge, Alert, Table, ScrollArea, Tabs, Card, ActionIcon, Divider, Code, Loader } from '@mantine/core';
import { IconAlertCircle, IconChevronDown, IconChevronRight } from '@tabler/icons-react';
import { LabExecuteResponse, LabAttemptResponse, DatabaseState } from '@/types/lab.types';

interface LabResultsPanelProps {
  result: LabExecuteResponse | null;
  attempts: LabAttemptResponse[];
  databaseState: DatabaseState | null;
  isLoadingDatabase: boolean;
}

export function LabResultsPanel({ result, attempts, databaseState, isLoadingDatabase }: LabResultsPanelProps) {
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());

  const toggleTable = (tableName: string) => {
    const newExpanded = new Set(expandedTables);
    if (newExpanded.has(tableName)) {
      newExpanded.delete(tableName);
    } else {
      newExpanded.add(tableName);
    }
    setExpandedTables(newExpanded);
  };
  return (
    <Tabs defaultValue="results" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Tabs.List>
        <Tabs.Tab value="results">Results</Tabs.Tab>
        <Tabs.Tab value="history">
          History
          {attempts.length > 0 && (
            <Badge size="xs" ml="xs" circle>
              {attempts.length}
            </Badge>
          )}
        </Tabs.Tab>
        <Tabs.Tab value="database">
          Database
          {databaseState && databaseState.tables.length > 0 && (
            <Badge size="xs" ml="xs" circle>
              {databaseState.tables.length}
            </Badge>
          )}
        </Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="results" style={{ flex: 1, overflow: 'auto' }}>
        {!result ? (
          <Stack align="center" justify="center" p="md" style={{ height: '100%' }}>
            <Text c="dimmed">Run a query to see results</Text>
          </Stack>
        ) : (
          <Stack gap="md" p="md">
            <Group justify="space-between" wrap="nowrap">
              <Text fw={500}>Results</Text>
              <Group gap="xs" wrap="nowrap">
                <Badge color={result.success ? 'green' : 'red'} size="sm">
                  {result.success ? 'Success' : 'Failed'}
                </Badge>
                {result.success && (
                  <Badge color="blue" size="sm">
                    {result.row_count} rows
                  </Badge>
                )}
                <Badge color="gray" size="sm">
                  {result.execution_time_ms.toFixed(2)}ms
                </Badge>
              </Group>
            </Group>

            {!result.success && result.error_message && (
              <Alert color="red" icon={<IconAlertCircle size={16} />}>
                {result.error_message}
              </Alert>
            )}

            {result.success && result.results.length > 0 && (
              <ScrollArea>
                <Table striped highlightOnHover withTableBorder withColumnBorders>
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
                            {row[col] !== null ? String(row[col]) : 'NULL'}
                          </Table.Td>
                        ))}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            )}

            {result.success && result.results.length === 0 && (
              <Text c="dimmed">Query executed successfully. No rows returned.</Text>
            )}
          </Stack>
        )}
      </Tabs.Panel>

      <Tabs.Panel value="history" style={{ flex: 1, overflow: 'auto' }}>
        <Stack gap="md" p="md">
          {attempts.length === 0 ? (
            <Text c="dimmed" ta="center" py="xl">
              No query history yet. Execute queries to see them here.
            </Text>
          ) : (
            attempts.map((attempt) => (
              <Card key={attempt.id} withBorder padding="sm" radius="md">
                <Stack gap="xs">
                  <Group justify="space-between" wrap="nowrap">
                    <Badge color={attempt.success ? 'green' : 'red'} size="sm">
                      {attempt.success ? 'Success' : 'Failed'}
                    </Badge>
                    <Group gap="xs" wrap="nowrap">
                      {attempt.success && (
                        <Badge color="blue" size="xs">
                          {attempt.row_count} rows
                        </Badge>
                      )}
                      <Badge color="gray" size="xs">
                        {attempt.execution_time_ms.toFixed(2)}ms
                      </Badge>
                    </Group>
                  </Group>

                  <Text size="xs" c="dimmed">
                    {new Date(attempt.submitted_at).toLocaleString()}
                  </Text>

                  <Text
                    size="sm"
                    style={{
                      fontFamily: 'monospace',
                      background: 'var(--mantine-color-gray-0)',
                      padding: '8px',
                      borderRadius: '4px',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {attempt.query.length > 150
                      ? `${attempt.query.substring(0, 150)}...`
                      : attempt.query}
                  </Text>

                  {!attempt.success && attempt.error_message && (
                    <Alert color="red" p="xs">
                      <Text size="xs">{attempt.error_message}</Text>
                    </Alert>
                  )}
                </Stack>
              </Card>
            ))
          )}
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="database" style={{ flex: 1, overflow: 'auto' }}>
        {isLoadingDatabase ? (
          <Stack align="center" justify="center" p="md" style={{ height: '100%' }}>
            <Loader size="sm" />
            <Text c="dimmed">Loading database state...</Text>
          </Stack>
        ) : !databaseState ? (
          <Stack align="center" justify="center" p="md" style={{ height: '100%' }}>
            <Text c="dimmed">No database state available</Text>
          </Stack>
        ) : databaseState.tables.length === 0 ? (
          <Stack align="center" justify="center" p="md" style={{ height: '100%' }}>
            <Text c="dimmed">No tables in database</Text>
          </Stack>
        ) : (
          <Stack gap="md" p="md">
            {databaseState.tables.map((table) => (
              <Card key={table.name} withBorder padding="sm" radius="md">
                <Stack gap="xs">
                  {/* Table Header */}
                  <Group justify="space-between" wrap="nowrap">
                    <Group gap="xs">
                      <ActionIcon
                        variant="subtle"
                        onClick={() => toggleTable(table.name)}
                        size="sm"
                      >
                        {expandedTables.has(table.name) ? (
                          <IconChevronDown size={16} />
                        ) : (
                          <IconChevronRight size={16} />
                        )}
                      </ActionIcon>
                      <Text fw={600} size="sm">{table.name}</Text>
                    </Group>
                    <Badge color="blue" size="sm">{table.row_count} rows</Badge>
                  </Group>

                  {/* Collapsed View: Column Names */}
                  {!expandedTables.has(table.name) && (
                    <Text size="xs" c="dimmed">
                      {table.columns.map(col => col.name).join(', ')}
                    </Text>
                  )}

                  {/* Expanded View: Full Schema + Data */}
                  {expandedTables.has(table.name) && (
                    <>
                      {/* Schema */}
                      <Divider />
                      <Text size="xs" fw={500}>Schema:</Text>
                      <Code block style={{ fontSize: '11px' }}>
                        {table.columns.map(col =>
                          `${col.name} ${col.type}${col.pk ? ' PRIMARY KEY' : ''}${col.notnull ? ' NOT NULL' : ''}`
                        ).join('\n')}
                      </Code>

                      {/* Sample Data */}
                      {table.sample_data.rows.length > 0 && (
                        <>
                          <Divider />
                          <Text size="xs" fw={500}>
                            Data Preview ({table.sample_data.rows.length} of {table.row_count} rows):
                          </Text>
                          <ScrollArea>
                            <Table striped highlightOnHover withTableBorder withColumnBorders size="xs">
                              <Table.Thead>
                                <Table.Tr>
                                  {table.sample_data.columns.map((col) => (
                                    <Table.Th key={col}>{col}</Table.Th>
                                  ))}
                                </Table.Tr>
                              </Table.Thead>
                              <Table.Tbody>
                                {table.sample_data.rows.map((row, idx) => (
                                  <Table.Tr key={idx}>
                                    {table.sample_data.columns.map((col) => (
                                      <Table.Td key={col}>
                                        {row[col] !== null ? String(row[col]) : 'NULL'}
                                      </Table.Td>
                                    ))}
                                  </Table.Tr>
                                ))}
                              </Table.Tbody>
                            </Table>
                          </ScrollArea>
                        </>
                      )}
                    </>
                  )}
                </Stack>
              </Card>
            ))}
          </Stack>
        )}
      </Tabs.Panel>
    </Tabs>
  );
}
