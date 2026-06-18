'use client';

import { useEffect, useState } from 'react';
import {
  Badge, Box, Button, Code, Divider, Group, Loader, ScrollArea, Select, Stack, Table, Tabs, Text, Title,
} from '@mantine/core';
import { IconCheck, IconPlayerPlay, IconRefresh } from '@tabler/icons-react';
import Editor from '@monaco-editor/react';
import { notifications } from '@mantine/notifications';
import { DatabaseState, ItemGradeResult, SqlLabRunResult } from '@/types/unified-lab.types';
import { SqlLabSolverQuestion } from '@/types/sql-lab-question.types';

// A main-style 3-panel SQL-lab workspace, driven entirely by injected actions so the SAME
// component renders both inside a lab and standalone (Problems tab) — just wired to different endpoints.
export interface SqlLabSolverProps {
  loadQuestion: () => Promise<SqlLabSolverQuestion>;
  run: (query: string) => Promise<SqlLabRunResult>;
  submit: (query: string, taskId: number) => Promise<ItemGradeResult>;
  getDatabase: () => Promise<DatabaseState>;
  reset: () => Promise<void>;
  onGraded?: () => void;
}

interface HistoryEntry {
  query: string;
  success: boolean;
  rowCount: number;
  error: string | null;
  at: string;
}

function ResultsGrid({ columns, rows }: { columns: string[]; rows: Array<Record<string, unknown>> }) {
  if (columns.length === 0) return null;
  return (
    <Table withTableBorder striped>
      <Table.Thead><Table.Tr>{columns.map((c) => <Table.Th key={c}>{c}</Table.Th>)}</Table.Tr></Table.Thead>
      <Table.Tbody>{rows.slice(0, 50).map((row, i) => (
        <Table.Tr key={i}>{columns.map((c) => <Table.Td key={c}>{String(row[c] ?? '')}</Table.Td>)}</Table.Tr>
      ))}</Table.Tbody>
    </Table>
  );
}

export function SqlLabSolver({ loadQuestion, run, submit, getDatabase, reset, onGraded }: SqlLabSolverProps) {
  const [question, setQuestion] = useState<SqlLabSolverQuestion | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<SqlLabRunResult | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [dbState, setDbState] = useState<DatabaseState | null>(null);
  const [passed, setPassed] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadQuestion()
      .then((q) => { setQuestion(q); setTaskId(q.tasks[0] ? String(q.tasks[0].id) : null); })
      .catch(() => setQuestion(null))
      .finally(() => setLoading(false));
    // Mount-only: callers `key` this per item/question, so a switch remounts + reloads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshDb = async () => { try { setDbState(await getDatabase()); } catch { /* ignore */ } };

  const doRun = async () => {
    setBusy(true);
    try {
      const r = await run(query);
      setResult(r);
      setHistory((h) => [
        { query, success: r.success, rowCount: r.row_count, error: r.error_message, at: new Date().toLocaleTimeString() },
        ...h,
      ].slice(0, 50));
      refreshDb();
    } catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Run failed' }); }
    finally { setBusy(false); }
  };

  const doSubmit = async () => {
    if (!taskId) return;
    setBusy(true);
    try {
      const res = await submit(query, Number(taskId));
      notifications.show({ color: res.is_passed ? 'green' : 'red', message: res.message });
      if (res.is_passed) setPassed((p) => new Set(p).add(Number(taskId)));
      onGraded?.();
    } catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Submit failed' }); }
    finally { setBusy(false); }
  };

  const doReset = async () => {
    setResetting(true);
    try {
      await reset();
      setResult(null);
      await refreshDb();
      notifications.show({ color: 'blue', message: 'Database reset to its starting state' });
    } catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Reset failed' }); }
    finally { setResetting(false); }
  };

  if (loading) return <Group justify="center" py="xl"><Loader /></Group>;
  if (!question) return <Text c="dimmed">Question not found.</Text>;

  const activeTask = question.tasks.find((t) => String(t.id) === taskId);

  return (
    <Box style={{ display: 'flex', gap: 12, alignItems: 'stretch', height: '72vh' }}>
      {/* LEFT: description + schema + tasks */}
      <Box style={{ flex: '0 0 30%', minWidth: 260, border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8, overflow: 'hidden' }}>
        <Tabs defaultValue="description" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Tabs.List>
            <Tabs.Tab value="description">Description</Tabs.Tab>
            <Tabs.Tab value="tasks">Tasks</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="description" style={{ flex: 1, overflow: 'hidden' }}>
            <ScrollArea h="100%" p="md">
              <Title order={4}>{question.title}</Title>
              <Text size="sm" mt="xs">{question.description}</Text>
              <Divider my="sm" />
              <Text size="sm" fw={600} mb={4}>Database schema</Text>
              <Code block style={{ fontSize: 12 }}>{question.schema_sql}</Code>
              <Text size="sm" fw={600} mt="sm" mb={4}>Seed data</Text>
              <Code block style={{ fontSize: 12 }}>{question.sample_data_sql}</Code>
            </ScrollArea>
          </Tabs.Panel>
          <Tabs.Panel value="tasks" style={{ flex: 1, overflow: 'hidden' }}>
            <ScrollArea h="100%" p="md">
              <Stack gap="xs">
                {question.tasks.map((t, i) => (
                  <Box key={t.id} onClick={() => setTaskId(String(t.id))}
                       style={{ cursor: 'pointer', border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8, padding: 8,
                                background: String(t.id) === taskId ? 'var(--mantine-color-gray-1)' : undefined }}>
                    <Group justify="space-between" wrap="nowrap">
                      <Text size="sm" fw={500}>{i + 1}. {t.title}</Text>
                      {passed.has(t.id) && <Badge size="xs" color="green" variant="light">Done</Badge>}
                    </Group>
                    <Text size="xs" c="dimmed" mt={2}>{t.description}</Text>
                  </Box>
                ))}
                {question.tasks.length === 0 && <Text size="sm" c="dimmed">No tasks.</Text>}
              </Stack>
            </ScrollArea>
          </Tabs.Panel>
        </Tabs>
      </Box>

      {/* CENTER: editor */}
      <Box style={{ flex: 1, minWidth: 320, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <Group justify="space-between">
          <Select size="xs" placeholder="Select task" style={{ width: 280 }}
                  data={question.tasks.map((t) => ({ value: String(t.id), label: t.title }))}
                  value={taskId} onChange={setTaskId} />
          <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />} onClick={doReset} loading={resetting}>
            Reset DB
          </Button>
        </Group>
        {activeTask && <Text size="sm" c="dimmed">{activeTask.description}</Text>}
        <Box style={{ flex: 1, border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8, overflow: 'hidden', minHeight: 200 }}>
          <Editor height="100%" defaultLanguage="sql" value={query} onChange={(v) => setQuery(v ?? '')} />
        </Box>
        <Group>
          <Button leftSection={<IconPlayerPlay size={16} />} variant="light" onClick={doRun} loading={busy}>Run</Button>
          <Button leftSection={<IconCheck size={16} />} color="green" onClick={doSubmit} loading={busy} disabled={!taskId}>
            Submit{activeTask ? `: ${activeTask.title}` : ''}
          </Button>
          <Text size="xs" c="dimmed">Your changes to the database persist across tasks.</Text>
        </Group>
      </Box>

      {/* RIGHT: results / history / database */}
      <Box style={{ flex: '0 0 34%', minWidth: 280, border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8, overflow: 'hidden' }}>
        <Tabs defaultValue="results" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
              onChange={(v) => { if (v === 'database') refreshDb(); }}>
          <Tabs.List>
            <Tabs.Tab value="results">Results</Tabs.Tab>
            <Tabs.Tab value="history">History</Tabs.Tab>
            <Tabs.Tab value="database">Database</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="results" style={{ flex: 1, overflow: 'hidden' }}>
            <ScrollArea h="100%" p="md">
              {!result && <Text size="sm" c="dimmed">Run a query to see results.</Text>}
              {result && (
                <Stack gap="xs">
                  <Group gap="xs">
                    <Badge color={result.success ? 'green' : 'red'} variant="light">{result.success ? 'Success' : 'Failed'}</Badge>
                    {result.success && <Badge variant="light">{result.row_count} rows</Badge>}
                  </Group>
                  {result.error_message && <Text c="red" size="sm">{result.error_message}</Text>}
                  <ResultsGrid columns={result.columns} rows={result.results} />
                </Stack>
              )}
            </ScrollArea>
          </Tabs.Panel>

          <Tabs.Panel value="history" style={{ flex: 1, overflow: 'hidden' }}>
            <ScrollArea h="100%" p="md">
              {history.length === 0 && <Text size="sm" c="dimmed">No attempts yet this session.</Text>}
              <Stack gap="xs">
                {history.map((h, i) => (
                  <Box key={i} style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8, padding: 8 }}>
                    <Group justify="space-between">
                      <Badge size="xs" color={h.success ? 'green' : 'red'} variant="light">{h.success ? `${h.rowCount} rows` : 'Failed'}</Badge>
                      <Text size="xs" c="dimmed">{h.at}</Text>
                    </Group>
                    <Code block style={{ fontSize: 11, marginTop: 4 }}>{h.query}</Code>
                    {h.error && <Text size="xs" c="red">{h.error}</Text>}
                  </Box>
                ))}
              </Stack>
            </ScrollArea>
          </Tabs.Panel>

          <Tabs.Panel value="database" style={{ flex: 1, overflow: 'hidden' }}>
            <ScrollArea h="100%" p="md">
              <Group justify="flex-end" mb="xs">
                <Button size="xs" variant="subtle" leftSection={<IconRefresh size={14} />} onClick={refreshDb}>Refresh</Button>
              </Group>
              {!dbState && <Text size="sm" c="dimmed">Open this tab to load the current database state.</Text>}
              <Stack gap="md">
                {dbState?.tables.map((tbl) => (
                  <Box key={tbl.name}>
                    <Group gap="xs">
                      <Text size="sm" fw={600}>{tbl.name}</Text>
                      <Badge size="xs" variant="light">{tbl.row_count} rows</Badge>
                    </Group>
                    <Text size="xs" c="dimmed" mt={2}>{tbl.columns.map((c) => `${c.name} ${c.type}`).join(', ')}</Text>
                    {tbl.sample_rows.length > 0 && (
                      <Table withTableBorder striped mt={4}>
                        <Table.Thead><Table.Tr>{tbl.columns.map((c) => <Table.Th key={c.name}>{c.name}</Table.Th>)}</Table.Tr></Table.Thead>
                        <Table.Tbody>{tbl.sample_rows.slice(0, 20).map((row, i) => (
                          <Table.Tr key={i}>{tbl.columns.map((c) => <Table.Td key={c.name}>{String(row[c.name] ?? '')}</Table.Td>)}</Table.Tr>
                        ))}</Table.Tbody>
                      </Table>
                    )}
                  </Box>
                ))}
                {dbState && dbState.tables.length === 0 && <Text size="sm" c="dimmed">No tables.</Text>}
              </Stack>
            </ScrollArea>
          </Tabs.Panel>
        </Tabs>
      </Box>
    </Box>
  );
}
