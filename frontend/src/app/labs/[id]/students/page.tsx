'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Badge, Box, Button, Group, Modal, NumberInput, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { UserRole } from '@/types/user.types';
import { unifiedLabService } from '@/services/unifiedLab.service';
import { UnifiedLabStudent, UnifiedLabSubmissionView } from '@/types/unified-lab.types';

function StudentsView({ labId }: { labId: number }) {
  const [students, setStudents] = useState<UnifiedLabStudent[]>([]);
  const [selected, setSelected] = useState<UnifiedLabStudent | null>(null);
  const [subs, setSubs] = useState<UnifiedLabSubmissionView[]>([]);
  const [overrideSub, setOverrideSub] = useState<UnifiedLabSubmissionView | null>(null);
  const [earned, setEarned] = useState<number | string>(0);
  const [total, setTotal] = useState<number | string>(10);
  const [reason, setReason] = useState('');

  useEffect(() => { unifiedLabService.students(labId).then((r) => setStudents(r.students)); }, [labId]);

  const openStudent = async (s: UnifiedLabStudent) => {
    setSelected(s);
    setSubs(await unifiedLabService.submissions(labId, s.user_id));
  };

  const applyOverride = async () => {
    if (!overrideSub) return;
    try {
      await unifiedLabService.override(overrideSub.id, { score_earned: Number(earned), score_total: Number(total), reason });
      notifications.show({ color: 'green', message: 'Override applied' });
      setOverrideSub(null);
      if (selected) setSubs(await unifiedLabService.submissions(labId, selected.user_id));
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message || 'Override failed' });
    }
  };

  return (
    <Box p="xl" maw={900} mx="auto">
      <Title order={3} mb="md">Students</Title>
      <Table withTableBorder striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Email</Table.Th>
            <Table.Th>Passed</Table.Th>
            <Table.Th>Last submitted</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {students.map((s) => (
            <Table.Tr key={s.user_id}>
              <Table.Td>{s.email}</Table.Td>
              <Table.Td>{s.passed_items} / {s.total_items}</Table.Td>
              <Table.Td>{s.last_submitted_at ? new Date(s.last_submitted_at).toLocaleString() : '—'}</Table.Td>
              <Table.Td>
                <Button size="xs" variant="light" onClick={() => openStudent(s)}>View</Button>
              </Table.Td>
            </Table.Tr>
          ))}
          {students.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={4}>
                <Text c="dimmed" ta="center">No students have joined this lab yet.</Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>

      {/* Per-student submissions modal */}
      <Modal opened={selected !== null} onClose={() => setSelected(null)} title={selected?.email} size="lg">
        <Stack gap="sm">
          {subs.map((sub) => (
            <Group key={sub.id} justify="space-between">
              <Group gap="sm">
                <Badge variant="light">{sub.kind.toUpperCase()}</Badge>
                <Text size="sm">{sub.item_title}</Text>
                <Badge color={sub.is_passed ? 'green' : 'gray'} variant="light">
                  {sub.score_total != null
                    ? `${sub.override_score_earned ?? sub.score_earned}/${sub.override_score_total ?? sub.score_total}`
                    : (sub.is_passed ? 'pass' : 'fail')}
                </Badge>
              </Group>
              {sub.kind === 'erd' && (
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() => {
                    setOverrideSub(sub);
                    setEarned(sub.score_earned ?? 0);
                    setTotal(sub.score_total ?? 10);
                    setReason('');
                  }}
                >
                  Override
                </Button>
              )}
            </Group>
          ))}
          {subs.length === 0 && <Text c="dimmed">No submissions.</Text>}
        </Stack>
      </Modal>

      {/* Override score modal */}
      <Modal opened={overrideSub !== null} onClose={() => setOverrideSub(null)} title="Override score">
        <Stack>
          <NumberInput label="Earned" value={earned} onChange={setEarned} min={0} />
          <NumberInput label="Total" value={total} onChange={setTotal} min={1} />
          <TextInput label="Reason (optional)" value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
          <Button onClick={applyOverride}>Apply</Button>
        </Stack>
      </Modal>
    </Box>
  );
}

export default function LabStudentsPage() {
  const params = useParams<{ id: string }>();
  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <StudentsView labId={Number(params.id)} />
    </ProtectedRoute>
  );
}
