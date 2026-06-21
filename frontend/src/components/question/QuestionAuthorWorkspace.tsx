'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Badge, Box, Button, Grid, Group, Stack, Text, TextInput, Textarea, Title } from '@mantine/core';
import { IconPlayerPlay, IconCheck, IconRefresh } from '@tabler/icons-react';
import Editor from '@monaco-editor/react';
import { notifications } from '@mantine/notifications';
import { AuthorQuestion, QuestionAuthorConfig } from '@/types/question-author.types';
import { SqlLabRunResult, DatabaseState } from '@/types/unified-lab.types';
import { ResultsGrid } from './ResultsGrid';
import { DbStateView } from './DbStateView';
import { TaskRail } from './TaskRail';

export function QuestionAuthorWorkspace({ id, config }: { id: number; config: QuestionAuthorConfig }) {
  const router = useRouter();
  const svc = config.service;
  const [q, setQ] = useState<AuthorQuestion | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tTitle, setTTitle] = useState('');
  const [tDesc, setTDesc] = useState('');
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<SqlLabRunResult | null>(null);
  const [db, setDb] = useState<DatabaseState | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { svc.getById(id).then((fresh) => { setQ(fresh); setSelectedId(fresh.tasks[0]?.id ?? null); }); /* eslint-disable-next-line */ }, [id]);
  const selected = q?.tasks.find((t) => t.id === selectedId) ?? null;
  useEffect(() => { setTTitle(selected?.title ?? ''); setTDesc(selected?.description ?? ''); }, [selectedId]); // eslint-disable-line

  const addTask = async () => { const fresh = await svc.addTask(id, { title: `Task ${(q?.tasks.length ?? 0) + 1}`, description: '' }); setQ(fresh); setSelectedId(fresh.tasks[fresh.tasks.length - 1]?.id ?? null); };
  const saveTaskText = async () => { if (!selectedId) return; setQ(await svc.updateTask(id, selectedId, { title: tTitle, description: tDesc })); };
  const move = async (taskId: number, dir: -1 | 1) => {
    if (!q) return;
    const ids = q.tasks.map((t) => t.id);
    const idx = ids.indexOf(taskId); const swap = idx + dir;
    if (swap < 0 || swap >= ids.length) return;
    [ids[idx], ids[swap]] = [ids[swap], ids[idx]];
    setQ(await svc.reorderTasks(id, ids));
  };
  const del = async (taskId: number) => { const fresh = await svc.deleteTask(id, taskId); setQ(fresh); if (selectedId === taskId) setSelectedId(fresh.tasks[0]?.id ?? null); };

  const run = async () => {
    setBusy(true);
    try { const r = await svc.run(id, query); setResult(r); setDb(await svc.database(id)); }
    catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Run failed' }); }
    finally { setBusy(false); }
  };
  const setAsAnswer = async () => {
    if (!selectedId) return;
    setBusy(true);
    try { setQ(await svc.assignAnswer(id, selectedId, query)); notifications.show({ color: 'green', message: 'Answer set from this query' }); }
    catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Could not set answer' }); }
    finally { setBusy(false); }
  };
  const resetDb = async () => { await svc.reset(id); setDb(await svc.database(id)); setResult(null); };
  const finalize = async () => {
    try { await svc.finalize(id); notifications.show({ color: 'green', message: 'Question finalized' }); router.push(config.poolHref); }
    catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Finalize blocked' }); }
  };

  if (!q) return <Box p="xl"><Text c="dimmed">Loading…</Text></Box>;
  const allAnswered = q.tasks.length > 0 && q.tasks.every((t) => t.has_answer);

  return (
    <Box p="md">
      <Group justify="space-between" mb="sm">
        <Group><Title order={3}>{q.title}</Title><Badge color={q.status === 'ready' ? 'green' : 'yellow'}>{q.status}</Badge></Group>
        <Button disabled={!allAnswered} onClick={finalize}>Finalize</Button>
      </Group>
      <Grid>
        <Grid.Col span={3}>
          <TaskRail tasks={q.tasks} selectedId={selectedId} onSelect={setSelectedId} onAdd={addTask} onMove={move} onDelete={del} />
        </Grid.Col>
        <Grid.Col span={5}>
          <Stack gap="xs">
            <Box style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8 }}>
              <Editor height="220px" defaultLanguage={config.editorLanguage} value={query} onChange={(v) => setQuery(v ?? '')} />
            </Box>
            <Group>
              <Button size="xs" leftSection={<IconPlayerPlay size={14} />} loading={busy} onClick={run}>Run</Button>
              <Button size="xs" variant="light" leftSection={<IconCheck size={14} />} disabled={!selectedId} onClick={setAsAnswer}>Set as correct answer</Button>
              <Button size="xs" variant="subtle" leftSection={<IconRefresh size={14} />} onClick={resetDb}>Reset DB</Button>
            </Group>
            {selected && (
              <Stack gap={4}>
                <TextInput label="Task title" value={tTitle} onChange={(e) => setTTitle(e.currentTarget.value)} onBlur={saveTaskText} />
                <Textarea label="Prompt shown to students" value={tDesc} onChange={(e) => setTDesc(e.currentTarget.value)} onBlur={saveTaskText} autosize minRows={2} />
              </Stack>
            )}
          </Stack>
        </Grid.Col>
        <Grid.Col span={4}>
          <Stack gap="xs">
            <Text fw={600} size="sm">Results</Text>
            {result && <ResultsGrid columns={result.columns} rows={result.results} />}
            <Text fw={600} size="sm" mt="sm">Database</Text>
            <DbStateView db={db} />
          </Stack>
        </Grid.Col>
      </Grid>
    </Box>
  );
}
