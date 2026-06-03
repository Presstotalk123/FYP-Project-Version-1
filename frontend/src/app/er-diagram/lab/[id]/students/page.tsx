'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Stack, Title, Table, Text } from '@mantine/core';
import { erLabsService } from '@/services/erLabs.service';
import type { ErLabStudentsResponse } from '@/types/er-lab.types';

export default function ErLabStudentsPage() {
  const params = useParams();
  const router = useRouter();
  const labId = Number(params.id);
  const [data, setData] = useState<ErLabStudentsResponse | null>(null);

  useEffect(() => { erLabsService.students(labId).then(setData); }, [labId]);
  if (!data) return null;

  return (
    <Stack p="md">
      <Title order={2}>{data.lab_title} — Students</Title>
      <Text c="dimmed">{data.total_questions} questions in this lab.</Text>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Student</Table.Th>
            <Table.Th>Total</Table.Th>
            <Table.Th>Attempts</Table.Th>
            <Table.Th>Last submission</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {data.students.map(s => (
            <Table.Tr key={s.user_id} style={{ cursor: 'pointer' }}
                      onClick={() => router.push(`/er-diagram/lab/${labId}/students/${s.user_id}`)}>
              <Table.Td>{s.email}</Table.Td>
              <Table.Td>
                {s.total_total > 0
                  ? `${s.total_earned.toFixed(1)} / ${s.total_total.toFixed(1)} (${((s.total_earned/s.total_total)*100).toFixed(0)}%)`
                  : '—'}
              </Table.Td>
              <Table.Td>{s.attempts}</Table.Td>
              <Table.Td>{s.last_submission_at ? new Date(s.last_submission_at).toLocaleString() : '—'}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
