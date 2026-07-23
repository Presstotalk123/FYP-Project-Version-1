'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Modal,
  Table,
  Loader,
  Alert,
  Badge,
  Text,
  Group,
  Stack,
  Button,
  Select,
} from '@mantine/core';
import { IconAlertCircle, IconUsers, IconPlayerPlay } from '@tabler/icons-react';
import { labService } from '@/services/lab.service';
import { LabStudentAttemptsResponse } from '@/types/lab.types';

interface StudentAttemptsModalProps {
  opened: boolean;
  onClose: () => void;
  labId: number;
  labTitle: string;
}

export function StudentAttemptsModal({
  opened,
  onClose,
  labId,
  labTitle,
}: StudentAttemptsModalProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<LabStudentAttemptsResponse | null>(null);
  const [selectedClassGroup, setSelectedClassGroup] = useState<string | null>(null);

  // Compute unique class groups for filter dropdown
  const classGroups = data 
    ? Array.from(new Set(data.students.map(s => s.class_group).filter((c): c is string => !!c))).sort()
    : [];

  // Filter students by selected class group
  const filteredStudents = data
    ? data.students.filter(s => !selectedClassGroup || s.class_group === selectedClassGroup)
    : [];

  useEffect(() => {
    if (opened) {
      setSelectedClassGroup(null); // Reset filter on open
      fetchStudentAttempts();
    }
  }, [opened, labId]);

  const fetchStudentAttempts = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await labService.getStudentAttempts(labId);
      setData(result);
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to load student attempts');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`Student Progress: ${labTitle}`}
      size="xl"
      styles={{
        title: { fontSize: '1.25rem', fontWeight: 600 },
      }}
    >
      <Stack gap="md">
        {loading && (
          <Group justify="center" py="xl">
            <Loader size="lg" />
          </Group>
        )}

        {error && (
          <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
            {error}
          </Alert>
        )}

        {!loading && !error && data && data.students.length === 0 && (
          <Alert icon={<IconUsers size={16} />} color="blue" title="No Submissions">
            No students have submitted attempts for this lab yet.
          </Alert>
        )}

        {!loading && !error && data && data.students.length > 0 && (
          <>
            <Group justify="space-between" align="flex-end">
              <Text size="md" fw={500} c="dimmed">
                Total Tasks: {data.total_tasks} | Total Students: {data.students.length}
                {selectedClassGroup && ` | Filtered: ${filteredStudents.length}`}
              </Text>
              
              {classGroups.length > 0 && (
                <Select
                  placeholder="Filter by Class Group"
                  data={classGroups}
                  value={selectedClassGroup}
                  onChange={setSelectedClassGroup}
                  clearable
                  searchable
                  style={{ width: 250 }}
                />
              )}
            </Group>
            
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th style={{ fontSize: '0.95rem' }}>Student Email</Table.Th>
                  <Table.Th style={{ fontSize: '0.95rem' }}>Correct</Table.Th>
                  <Table.Th style={{ fontSize: '0.95rem' }}>Not Solved</Table.Th>
                  <Table.Th style={{ fontSize: '0.95rem' }}>Total Tasks</Table.Th>
                  <Table.Th style={{ fontSize: '0.95rem' }}>Last Activity</Table.Th>
                  <Table.Th style={{ fontSize: '0.95rem' }}>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filteredStudents.map((student) => (
                  <Table.Tr key={student.user_id}>
                    <Table.Td>
                      <Text size="md" fw={500}>{student.email}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color="green" variant="light" size="lg">
                        {student.correct_count}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Badge color="orange" variant="light" size="lg">
                        {student.not_solved_count}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="md" fw={500}>{student.total_tasks}</Text>
                    </Table.Td>
                    <Table.Td>
                      {student.last_submission_at ? (
                        <Text size="md">
                          {new Date(student.last_submission_at).toLocaleDateString()}{' '}
                          {new Date(student.last_submission_at).toLocaleTimeString()}
                        </Text>
                      ) : (
                        <Text size="md" c="dimmed">
                          Never
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Button
                        size="sm"
                        variant="light"
                        color="violet"
                        leftSection={<IconPlayerPlay size={16} />}
                        onClick={() => {
                          router.push(`/admin/labs/${labId}/review/${student.user_id}`);
                          onClose();
                        }}
                      >
                        Review Activity
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </>
        )}
      </Stack>
    </Modal>
  );
}
