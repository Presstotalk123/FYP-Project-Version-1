'use client';
import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { Stack, Title, Card, Group, Text, Badge } from '@mantine/core';
import { erLabsService } from '@/services/erLabs.service';
import type { ErLabSubmissionResponse, ErLabQuestionResponse } from '@/types/er-lab.types';

export default function StudentErLabHistoryPage() {
  const params = useParams();
  const labId = Number(params.id);
  const [subs, setSubs] = useState<ErLabSubmissionResponse[]>([]);
  const [qs, setQs] = useState<ErLabQuestionResponse[]>([]);

  useEffect(() => {
    erLabsService.mySubmissions(labId).then(setSubs);
    erLabsService.listQuestions(labId).then(setQs);
  }, [labId]);

  const qMap = useMemo(() => new Map(qs.map(q => [q.id, q])), [qs]);

  return (
    <Stack p="md">
      <Title order={2}>My submission history</Title>
      {subs.length === 0 && <Text c="dimmed">No submissions yet.</Text>}
      {subs.map(s => {
        const q = qMap.get(s.er_lab_question_id);
        const effective = s.override_score_percent ?? s.auto_score_percent;
        return (
          <Card key={s.id} withBorder>
            <Group justify="space-between">
              <Stack gap={0}>
                <Text fw={600}>{q?.title ?? `Question ${s.er_lab_question_id}`}</Text>
                <Text size="sm" c="dimmed">{new Date(s.submitted_at).toLocaleString()}</Text>
              </Stack>
              <Group>
                <Badge color={s.override_score_percent != null ? 'orange' : 'blue'}>
                  {effective.toFixed(1)}%
                </Badge>
                {s.override_score_percent != null && <Badge color="orange">Adjusted by staff</Badge>}
              </Group>
            </Group>
          </Card>
        );
      })}
    </Stack>
  );
}
