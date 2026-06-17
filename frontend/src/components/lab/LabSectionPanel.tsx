'use client';

import { useEffect, useState } from 'react';
import { Box, Button, Group, Select, Stack, Table, Text } from '@mantine/core';
import Editor from '@monaco-editor/react';
import { notifications } from '@mantine/notifications';
import { labService } from '@/services/lab.service';
import { unifiedLabService } from '@/services/unifiedLab.service';
import { LabTask, LabExecuteResponse } from '@/types/lab.types';

export function LabSectionPanel({ labId, itemId, sessionId, onGraded }: {
  labId: number; itemId: number; sessionId: number; onGraded: () => void;
}) {
  const [tasks, setTasks] = useState<LabTask[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<LabExecuteResponse | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { labService.getLabTasks(labId).then((t) => { setTasks(t); setTaskId(t[0] ? String(t[0].id) : null); }); }, [labId]);

  const run = async () => { setBusy(true); try { setResult(await labService.executeQuery(sessionId, query)); } catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Run failed' }); } finally { setBusy(false); } };
  const submit = async () => {
    if (!taskId) return;
    setBusy(true);
    try {
      const res = await unifiedLabService.submitItem(labId, itemId, query, Number(taskId));
      notifications.show({ color: res.is_passed ? 'green' : 'red', message: res.message });
      onGraded();
    } catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Submit failed' }); }
    finally { setBusy(false); }
  };

  return (
    <Stack gap="md">
      <Select label="Task" data={tasks.map((t) => ({ value: String(t.id), label: t.title }))} value={taskId} onChange={setTaskId} />
      <Text size="sm" c="dimmed">{tasks.find((t) => String(t.id) === taskId)?.description}</Text>
      <Box style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8 }}>
        <Editor height="180px" defaultLanguage="sql" value={query} onChange={(v) => setQuery(v ?? '')} />
      </Box>
      <Group>
        <Button variant="light" onClick={run} loading={busy}>Run</Button>
        <Button onClick={submit} loading={busy} disabled={!taskId}>Submit</Button>
        <Text size="xs" c="dimmed">Your edits persist across tasks in this section.</Text>
      </Group>
      {result?.error_message && <Text c="red" size="sm">{result.error_message}</Text>}
      {result && result.columns.length > 0 && (
        <Table withTableBorder striped>
          <Table.Thead><Table.Tr>{result.columns.map((c) => <Table.Th key={c}>{c}</Table.Th>)}</Table.Tr></Table.Thead>
          <Table.Tbody>{result.results.slice(0, 50).map((row, i) => (
            <Table.Tr key={i}>{result.columns.map((c) => <Table.Td key={c}>{String((row as Record<string, unknown>)[c] ?? '')}</Table.Td>)}</Table.Tr>
          ))}</Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
