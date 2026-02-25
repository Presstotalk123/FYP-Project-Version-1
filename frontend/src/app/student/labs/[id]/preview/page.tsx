'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Container,
  Stack,
  Paper,
  Title,
  Text,
  Button,
  Group,
  Loader,
  Alert,
  Badge,
  Accordion,
  Code,
  Table,
} from '@mantine/core';
import { IconAlertCircle, IconArrowLeft } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { LabDetail, SchemaPreview } from '@/types/lab.types';
import { labService } from '@/services/lab.service';

export default function LabPreviewPage() {
  const params = useParams();
  const router = useRouter();
  const labId = parseInt(params.id as string);

  const [lab, setLab] = useState<LabDetail | null>(null);
  const [schema, setSchema] = useState<SchemaPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLabPreview();
  }, [labId]);

  const fetchLabPreview = async () => {
    try {
      setLoading(true);
      setError(null);

      const [labData, schemaData] = await Promise.all([
        labService.getLabById(labId),
        labService.getSchemaPreview(labId),
      ]);

      setLab(labData);
      setSchema(schemaData);
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to load lab preview');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <Container size="xl">
          {loading && (
            <Group justify="center" py="xl">
              <Loader size="lg" />
            </Group>
          )}

          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {error}
              <Button
                mt="md"
                variant="light"
                onClick={() => router.push('/student/labs')}
              >
                Back to Labs
              </Button>
            </Alert>
          )}

          {!loading && !error && lab && schema && (
            <Stack gap="md">
              <Group justify="space-between">
                <div>
                  <Title order={2}>{lab.title}</Title>
                  <Group mt="xs" gap="xs">
                    <Badge color="yellow">Preview Mode</Badge>
                    <Badge color="gray">Read Only</Badge>
                  </Group>
                </div>
                <Button
                  leftSection={<IconArrowLeft size={16} />}
                  variant="default"
                  onClick={() => router.push('/student/labs')}
                >
                  Back to Labs
                </Button>
              </Group>

              <Alert icon={<IconAlertCircle size={16} />} color="yellow" title="Lab Not Running">
                This lab is not currently running. You can preview the database schema below,
                but you cannot execute queries yet. Check back later when the lab is started.
              </Alert>

              <Paper shadow="xs" p="md" withBorder>
                <Text fw={500} mb="sm">Lab Description</Text>
                <Text size="sm" c="dimmed">{lab.description}</Text>
              </Paper>

              <Paper shadow="xs" p="md" withBorder>
                <Text fw={500} mb="md">Database Schema</Text>

                {schema.tables.length === 0 && (
                  <Text c="dimmed">No tables defined for this lab.</Text>
                )}

                {schema.tables.length > 0 && (
                  <Accordion variant="contained">
                    {schema.tables.map((table) => (
                      <Accordion.Item key={table.name} value={table.name}>
                        <Accordion.Control>
                          <Group>
                            <Text fw={500}>{table.name}</Text>
                            <Badge size="sm" color="blue">
                              {table.columns.length} columns
                            </Badge>
                          </Group>
                        </Accordion.Control>
                        <Accordion.Panel>
                          <Stack gap="md">
                            <div>
                              <Text size="sm" fw={500} mb="xs">Columns</Text>
                              <Table striped withTableBorder withColumnBorders>
                                <Table.Thead>
                                  <Table.Tr>
                                    <Table.Th>Column Name</Table.Th>
                                    <Table.Th>Type</Table.Th>
                                    <Table.Th>Constraints</Table.Th>
                                  </Table.Tr>
                                </Table.Thead>
                                <Table.Tbody>
                                  {table.columns.map((col) => (
                                    <Table.Tr key={col.name}>
                                      <Table.Td>
                                        <Text fw={col.pk ? 500 : 400}>
                                          {col.name}
                                          {col.pk && <Badge ml="xs" size="xs" color="yellow">PK</Badge>}
                                        </Text>
                                      </Table.Td>
                                      <Table.Td>
                                        <Code>{col.type}</Code>
                                      </Table.Td>
                                      <Table.Td>
                                        <Group gap="xs">
                                          {col.notnull && <Badge size="xs" color="red">NOT NULL</Badge>}
                                          {col.default_value && (
                                            <Badge size="xs" color="gray">
                                              DEFAULT: {col.default_value}
                                            </Badge>
                                          )}
                                        </Group>
                                      </Table.Td>
                                    </Table.Tr>
                                  ))}
                                </Table.Tbody>
                              </Table>
                            </div>

                            <div>
                              <Text size="sm" fw={500} mb="xs">CREATE TABLE Statement</Text>
                              <Code block>{table.create_sql}</Code>
                            </div>
                          </Stack>
                        </Accordion.Panel>
                      </Accordion.Item>
                    ))}
                  </Accordion>
                )}
              </Paper>
            </Stack>
          )}
        </Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
