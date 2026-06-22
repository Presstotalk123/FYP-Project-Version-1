'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Button, Group, Stack, Tabs, Title, Card, Text, Table, Badge,
  TextInput, Textarea, PasswordInput, ActionIcon, Menu,
} from '@mantine/core';
import { IconArrowLeft, IconDots, IconPlus } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { erLabsService } from '@/services/erLabs.service';
import type { ErLabStaffDetail, ErLabQuestionResponse } from '@/types/er-lab.types';

export default function ErLabDetailPage() {
  const params = useParams();
  const router = useRouter();
  const labId = Number(params.id);
  const [lab, setLab] = useState<ErLabStaffDetail | null>(null);
  const [questions, setQuestions] = useState<ErLabQuestionResponse[]>([]);

  const [settingsEditing, setSettingsEditing] = useState(false);
  const [settingsForm, setSettingsForm] = useState({ title: '', description: '', join_password: '' });

  const refresh = async () => {
    const [l, qs] = await Promise.all([
      erLabsService.get(labId) as Promise<ErLabStaffDetail>,
      erLabsService.listQuestions(labId),
    ]);
    setLab(l);
    setQuestions(qs);
    setSettingsForm({ title: l.title, description: l.description, join_password: l.join_password });
  };

  useEffect(() => {
    refresh().catch(e => notifications.show({ color: 'red', message: e.message }));
  }, [labId]);

  if (!lab) return null;

  const deleteQuestion = async (q: ErLabQuestionResponse) => {
    if (!confirm(`Delete "${q.title}"?`)) return;
    await erLabsService.deleteQuestion(labId, q.id);
    refresh();
  };

  const saveSettings = async () => {
    const patch: Partial<{ title: string; description: string; join_password: string }> = {};
    if (settingsForm.title !== lab.title) patch.title = settingsForm.title;
    if (settingsForm.description !== lab.description) patch.description = settingsForm.description;
    if (settingsForm.join_password !== lab.join_password) patch.join_password = settingsForm.join_password;
    if (Object.keys(patch).length === 0) {
      setSettingsEditing(false);
      return;
    }
    try {
      await erLabsService.update(labId, patch);
      notifications.show({ color: 'green', message: 'Settings updated' });
      setSettingsEditing(false);
      refresh();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Update failed';
      notifications.show({ color: 'red', message: msg });
    }
  };

  return (
    <Stack p="md">
      <Group justify="space-between">
        <Group align="center" gap="sm">
          <ActionIcon
            component="a"
            href="/er-diagram"
            variant="subtle"
            size="sm"
            aria-label="Back to ER diagram"
          >
            <IconArrowLeft size={18} />
          </ActionIcon>
          <Stack gap={0}>
            <Title order={2}>{lab.title}</Title>
            <Group gap={4}>
              <Badge color={lab.is_published ? 'green' : 'gray'}>{lab.is_published ? 'Published' : 'Unpublished'}</Badge>
              <Badge color={lab.is_running ? 'blue' : 'gray'}>{lab.is_running ? 'Running' : 'Stopped'}</Badge>
            </Group>
          </Stack>
        </Group>
        <Button variant="default" onClick={() => router.push(`/er-diagram/lab/${labId}/students`)}>
          View students
        </Button>
      </Group>

      <Tabs defaultValue="questions">
        <Tabs.List>
          <Tabs.Tab value="questions">Questions ({questions.length})</Tabs.Tab>
          <Tabs.Tab value="settings">Settings</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="questions" pt="md">
          <Group justify="space-between" mb="sm">
            <Text c="dimmed">Questions are ordered by order_index.</Text>
            <Button leftSection={<IconPlus size={16} />}
                    onClick={() => router.push(`/er-diagram/lab/${labId}/add-question`)}
                    disabled={!!lab.is_running}>
              Add question
            </Button>
          </Group>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>#</Table.Th>
                <Table.Th>Title</Table.Th>
                <Table.Th>Difficulty</Table.Th>
                <Table.Th></Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {questions.map(q => (
                <Table.Tr key={q.id}>
                  <Table.Td>{q.order_index}</Table.Td>
                  <Table.Td>{q.title}</Table.Td>
                  <Table.Td>{q.difficulty_label}</Table.Td>
                  <Table.Td>
                    <Menu>
                      <Menu.Target><ActionIcon variant="subtle"><IconDots /></ActionIcon></Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item onClick={() => router.push(`/er-diagram/lab/${labId}/edit-question/${q.id}`)}
                                   disabled={!!lab.is_running}>
                          Edit
                        </Menu.Item>
                        <Menu.Item color="red" disabled={!!lab.is_running}
                                   onClick={() => deleteQuestion(q)}>
                          Delete
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        <Tabs.Panel value="settings" pt="md">
          <Card withBorder>
            <Stack>
              <TextInput label="Title" value={settingsForm.title}
                         onChange={e => setSettingsForm(s => ({ ...s, title: e.target.value }))}
                         disabled={!settingsEditing} />
              <Textarea label="Description" value={settingsForm.description}
                        onChange={e => setSettingsForm(s => ({ ...s, description: e.target.value }))}
                        disabled={!settingsEditing} minRows={3} />
              <PasswordInput label="Join password" value={settingsForm.join_password}
                             onChange={e => setSettingsForm(s => ({ ...s, join_password: e.target.value }))}
                             visible disabled={!settingsEditing} />
              <Text size="sm" c="dimmed">
                Edits disabled while the lab is running. Stop the lab first.
              </Text>
              <Group>
                {settingsEditing
                  ? <>
                      <Button onClick={saveSettings}>Save</Button>
                      <Button variant="default" onClick={() => {
                        setSettingsEditing(false);
                        setSettingsForm({ title: lab.title, description: lab.description, join_password: lab.join_password });
                      }}>Cancel</Button>
                    </>
                  : <Button disabled={!!lab.is_running} onClick={() => setSettingsEditing(true)}>Edit</Button>}
              </Group>
            </Stack>
          </Card>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
