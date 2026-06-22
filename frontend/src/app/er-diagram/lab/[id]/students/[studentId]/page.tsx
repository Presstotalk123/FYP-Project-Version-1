'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { ActionIcon, Stack, Title, Card, Group, Text, Badge, Button, Modal, NumberInput, Textarea } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { erLabsService } from '@/services/erLabs.service';
import type { ErLabSubmissionResponse, ErLabQuestionResponse } from '@/types/er-lab.types';

export default function ErLabStudentDrillPage() {
  const params = useParams();
  const labId = Number(params.id);
  const studentId = Number(params.studentId);
  const [submissions, setSubmissions] = useState<ErLabSubmissionResponse[]>([]);
  const [questions, setQuestions] = useState<ErLabQuestionResponse[]>([]);
  const [overrideSub, setOverrideSub] = useState<ErLabSubmissionResponse | null>(null);
  const [earned, setEarned] = useState<number | string>(0);
  const [total, setTotal] = useState<number | string>(0);
  const [reason, setReason] = useState('');

  const refresh = async () => {
    const [s, q] = await Promise.all([
      erLabsService.mySubmissions(labId, studentId),
      erLabsService.listQuestions(labId),
    ]);
    setSubmissions(s); setQuestions(q);
  };
  useEffect(() => { refresh(); }, [labId, studentId]);

  const openOverride = (sub: ErLabSubmissionResponse) => {
    setOverrideSub(sub);
    setEarned(sub.override_score_earned ?? sub.auto_score_earned);
    setTotal(sub.override_score_total ?? sub.auto_score_total);
    setReason(sub.override_reason ?? '');
  };

  const submitOverride = async () => {
    if (!overrideSub) return;
    try {
      await erLabsService.setOverride(overrideSub.id, {
        score_earned: Number(earned),
        score_total: Number(total),
        reason,
      });
      notifications.show({ color: 'green', message: 'Override set' });
      setOverrideSub(null); refresh();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed';
      notifications.show({ color: 'red', message: msg });
    }
  };

  const clearOverride = async () => {
    if (!overrideSub) return;
    await erLabsService.clearOverride(overrideSub.id);
    notifications.show({ color: 'green', message: 'Override cleared' });
    setOverrideSub(null); refresh();
  };

  const qById = new Map(questions.map(q => [q.id, q]));

  return (
    <Stack p="md">
      <Group align="center" gap="sm">
        <ActionIcon
          component="a"
          href={`/er-diagram/lab/${labId}/students`}
          variant="subtle"
          size="sm"
          aria-label="Back to students summary"
        >
          <IconArrowLeft size={18} />
        </ActionIcon>
        <Title order={2}>Student submissions (chronological)</Title>
      </Group>
      {submissions.map(s => {
        const q = qById.get(s.er_lab_question_id);
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
                {s.override_score_percent != null && <Badge color="orange">Overridden</Badge>}
                <Button size="xs" variant="default" onClick={() => openOverride(s)}>Override</Button>
              </Group>
            </Group>
            {s.override_reason && <Text size="sm" mt="xs">Reason: {s.override_reason}</Text>}
          </Card>
        );
      })}

      <Modal opened={!!overrideSub} onClose={() => setOverrideSub(null)} title="Override score">
        <Stack>
          <NumberInput label="Earned points" value={earned}
                       onChange={setEarned} min={0} />
          <NumberInput label="Total points" value={total}
                       onChange={setTotal} min={0.01} />
          <Textarea label="Reason" value={reason} onChange={e => setReason(e.target.value)}
                    required minRows={3} />
          <Group justify="space-between">
            <Button variant="subtle" color="red" onClick={clearOverride}>Clear override</Button>
            <Button onClick={submitOverride}
                    disabled={!reason || Number(total) <= 0 || Number(earned) < 0}>
              Save override
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
