'use client';

import { useEffect, useState } from 'react';
import { Badge, Box, Button, Group, Stack, Table, Text, Title } from '@mantine/core';
import Editor from '@monaco-editor/react';
import { notifications } from '@mantine/notifications';
import { questionService } from '@/services/question.service';
import { executeService } from '@/services/execute.service';
import { unifiedLabService } from '@/services/unifiedLab.service';
import { LabItem } from '@/types/unified-lab.types';
import { QuestionDetail } from '@/types/question.types';
import { ExecuteResponse } from '@/types/attempt.types';

export function LabSqlItemPanel({ labId, item, onGraded }: {
  labId: number; item: LabItem; onGraded: () => void;
}) {
  const [question, setQuestion] = useState<QuestionDetail | null>(null);
  const [query, setQuery] = useState('SELECT * FROM ...;');
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (item.ref_id != null) questionService.getQuestionById(item.ref_id).then(setQuestion).catch(() => setQuestion(null));
  }, [item.ref_id]);

  const run = async () => {
    if (item.ref_id == null) return;
    setBusy(true);
    try { setResult(await executeService.executeQuery({ question_id: item.ref_id, query })); }
    catch (e) { notifications.show({ color: 'red', message: (e as Error).message || 'Run failed' }); }
    finally { setBusy(false); }
  };

  const submit = async () => {
    setBusy(true);
    try {
      const res = await unifiedLabService.submitItem(labId, item.id, query);
      notifications.show({ color: res.is_passed ? 'green' : 'red', message: res.message });
      onGraded();
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message || 'Submit failed' });
    } finally { setBusy(false); }
  };

  return (
    <Stack gap="md">
      <div>
        <Title order={4}>{question?.title ?? item.title}</Title>
        <Text c="dimmed" size="sm" mt={4}>{question?.description}</Text>
      </div>
      <Box style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8 }}>
        <Editor height="180px" defaultLanguage="sql" value={query} onChange={(v) => setQuery(v ?? '')} />
      </Box>
      <Group>
        <Button onClick={run} loading={busy} variant="light">Run</Button>
        <Button onClick={submit} loading={busy}>Submit</Button>
        {result && <Badge color={result.is_correct ? 'green' : 'gray'} variant="light">
          {result.is_correct ? 'Matches expected output' : `${result.row_count} rows`}</Badge>}
      </Group>
      {result?.error_message && <Text c="red" size="sm">{result.error_message}</Text>}
      {result && result.columns.length > 0 && (
        <Table withTableBorder striped>
          <Table.Thead><Table.Tr>{result.columns.map((c) => <Table.Th key={c}>{c}</Table.Th>)}</Table.Tr></Table.Thead>
          <Table.Tbody>
            {result.results.slice(0, 50).map((row, i) => (
              <Table.Tr key={i}>{result.columns.map((c) => <Table.Td key={c}>{String((row as Record<string, unknown>)[c] ?? '')}</Table.Td>)}</Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
