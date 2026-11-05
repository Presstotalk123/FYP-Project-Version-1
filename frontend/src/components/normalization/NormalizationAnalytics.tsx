'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Badge, Button, Card, Group, Loader, Modal, Select, Stack, Table, Text, Textarea, TextInput } from '@mantine/core';
import { normalizationService, normalizationError } from '@/services/normalization.service';
import { queryKeys } from '@/services/query-keys';
import { NormalizationFeedback } from './NormalizationWorkspace';
import type { NormalizationAttempt } from '@/types/normalization.types';
import styles from './NormalizationStaff.module.css';

export function NormalizationAnalytics({ questionId, studentId, onReviewed }: { questionId: number; studentId?: number; onReviewed?: () => void }) {
  const cache = useQueryClient();
  const [group, setGroup] = useState('');
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState<NormalizationAttempt | null>(null);
  const [decision, setDecision] = useState<'accepted' | 'rejected'>('accepted');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const query = useQuery({ queryKey: queryKeys.normalizationAnalytics(questionId, group), queryFn: () => normalizationService.analytics(questionId, group), refetchOnMount: true });
  if (query.isLoading) return <Loader />;
  if (query.error) return <Alert color="red">{normalizationError(query.error)}</Alert>;
  const data = query.data!;
  const rows = data.submissions.filter(s => (!studentId || s.user_id === studentId)
    && `${s.student_name ?? ''} ${s.student_email ?? ''}`.toLowerCase().includes(filter.toLowerCase()));
  async function resolve() {
    if (!selected) return;
    setSaving(true); setError('');
    try {
      setSelected(await normalizationService.review(selected.id, decision, reason, selected.review_version));
      setReason(''); await cache.invalidateQueries({ queryKey: ['normalization'] });
      await cache.invalidateQueries({ queryKey: queryKeys.assessmentAnalyticsSummary });
      await cache.invalidateQueries({ queryKey: ['assessmentStudents'] });
      await cache.invalidateQueries({ queryKey: ['assessmentItemAnalytics'] });
      onReviewed?.();
    } catch (e) { setError(normalizationError(e)); } finally { setSaving(false); }
  }
  return <Stack>
    <h3 style={{ margin: 0 }}>{data.question.title}</h3>
    <Group justify="space-between"><Text size="sm" c="dimmed">Submission overview and FD interpretation review</Text><Button variant="default" size="xs" onClick={() => query.refetch()}>Refresh</Button></Group>
    <div className={styles.metrics}><div className={styles.metric}><Text size="xs" c="dimmed">Students</Text><strong>{data.student_count}</strong></div><div className={styles.metric}><Text size="xs" c="dimmed">Submitted attempts</Text><strong>{data.attempt_count}</strong></div><div className={styles.metric}><Text size="xs" c="dimmed">Pending interpretations</Text><strong>{data.review_pending}</strong></div></div>
    <div className={styles.scoreSummary}><div><Text size="xs" c="dimmed">Mean FD score</Text><strong>{data.average_fd === null ? '—' : `${data.average_fd}%`}</strong></div><div><Text size="xs" c="dimmed">Mean normalization score</Text><strong>{data.average_normalization === null ? '—' : `${data.average_normalization}%`}</strong></div><div><Text size="xs" c="dimmed">Mean overall score</Text><strong>{data.average_score === null ? '—' : `${data.average_score}%`}</strong></div></div>
    <Text size="sm">Score distribution: {Object.entries(data.score_distribution).map(([range, count]) => `${range}%: ${count}`).join(' · ')}</Text>
    <Group grow><TextInput label="Class group" placeholder="All groups" value={group} onChange={e => setGroup(e.currentTarget.value)} />
      <TextInput label="Find student" value={filter} onChange={e => setFilter(e.currentTarget.value)} /></Group>
    <Table.ScrollContainer minWidth={600}><Table striped><Table.Thead><Table.Tr><Table.Th>Student</Table.Th><Table.Th>Class</Table.Th><Table.Th>Submitted</Table.Th><Table.Th>Result</Table.Th><Table.Th /></Table.Tr></Table.Thead>
      <Table.Tbody>{rows.map(row => <Table.Tr key={row.id}><Table.Td>{row.student_name || row.student_email}</Table.Td><Table.Td>{row.class_group || '—'}</Table.Td>
        <Table.Td>{row.created_at ? new Date(row.created_at).toLocaleString() : '—'}</Table.Td><Table.Td>{row.result ? `${row.result.score.overall_percent}% · ${row.result.decision}` : row.status}
          {row.reviews.at(-1)?.decision === 'requested' && <Badge color="yellow" ml="xs">Review requested</Badge>}</Table.Td>
        <Table.Td><Button size="xs" onClick={() => { setSelected(row); setError(''); setReason(''); }}>View submission</Button></Table.Td></Table.Tr>)}</Table.Tbody>
    </Table></Table.ScrollContainer>
    {!rows.length && <Text c="dimmed">No submissions match.</Text>}
    <Modal opened={!!selected} onClose={() => setSelected(null)} title="Submission and FD interpretation review" closeButtonProps={{ 'aria-label': 'Close submission review' }} size="xl">
      {selected && <Stack>
        <Text size="sm">Question version {selected.question_version} · Student #{selected.user_id}</Text>
        <Card withBorder><Text fw={700}>Submitted functional dependencies</Text>{selected.payload.functional_dependencies.map((fd, i) => <Text key={i}>{fd.lhs.join(', ')} → {fd.rhs.join(', ')}</Text>)}
          <Text mt="sm">Assumption: {selected.payload.assumption || 'None'}</Text></Card>
        <Card withBorder><Text fw={700}>Submitted decomposition</Text><Text>Root: {selected.payload.process.root.name} ({selected.payload.process.root.attributes.join(', ')})</Text>
          {selected.payload.process.steps.map(step => <Text size="sm" key={step.step_id}>{step.parent_node_id} — {step.selected_fd.lhs.join(', ')} → {step.selected_fd.rhs.join(', ')} — {step.children.map(c => `${c.name}(${c.attributes.join(', ')}), key(${c.primary_key.join(', ')})`).join(' / ')}</Text>)}
          {!selected.payload.process.steps.length && <Text size="sm">No splits submitted.</Text>}</Card>
        <NormalizationFeedback attempt={selected} />
        {selected.snapshot && <Card withBorder><Text fw={700}>Approved reference at submission</Text>{selected.snapshot.approved_fds.map((fd, i) => <Text size="sm" key={i}>{fd.lhs.join(', ')} → {fd.rhs.join(', ')}</Text>)}</Card>}
        {error && <Alert color="red">{error}</Alert>}
        <Select label="FD interpretation decision" value={decision} data={[{ value: 'accepted', label: 'Accept interpretation' }, { value: 'rejected', label: 'Reject interpretation' }]} onChange={v => setDecision(v as 'accepted' | 'rejected')} />
        <Textarea label="Reason (required, visible in review history)" value={reason} onChange={e => setReason(e.currentTarget.value)} maxLength={2000} />
        <Text size="sm" c="dimmed">This changes FD marks and the overall score. Formal normalization evidence and marks stay unchanged.</Text>
        <Button loading={saving} disabled={!reason.trim() || !selected.result} onClick={resolve}>Record staff decision</Button>
      </Stack>}
    </Modal>
  </Stack>;
}
