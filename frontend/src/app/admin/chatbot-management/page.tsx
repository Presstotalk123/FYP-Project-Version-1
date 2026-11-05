'use client';

import { useState } from 'react';
import { AkelaButton as Button } from '@/components/admin/chatbot-management/AkelaButton';
import { ChatbotManagementShell } from '@/components/admin/chatbot-management/ChatbotManagementShell';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Badge, Card, FileInput, Group, Loader, Modal, Select,
  SimpleGrid, Stack, Table, Tabs, Text, Textarea, TextInput, Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconPlus, IconRefresh, IconUpload } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { chatbotManagementService as service } from '@/services/chatbot-management.service';
import { getApiErrorMessage } from '@/utils/api-error';
import { useAuth } from '@/contexts/AuthContext';

function Management() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [course, setCourse] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [courseModal, setCourseModal] = useState(false);
  const [categoryModal, setCategoryModal] = useState(false);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [categoryName, setCategoryName] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [question, setQuestion] = useState('');
  const [conversationId, setConversationId] = useState<string>();
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [operationError, setOperationError] = useState<string | null>(null);
  const rootKey = ['chatbot-management', user?.id];
  const courses = useQuery({ queryKey: [...rootKey, 'courses'], queryFn: service.courses });
  const categories = useQuery({
    queryKey: [...rootKey, course, 'categories'], queryFn: () => service.categories(course!), enabled: !!course,
  });
  const documents = useQuery({
    queryKey: [...rootKey, course, category, 'files'], queryFn: () => service.files(course!, category!), enabled: !!course && !!category,
  });

  const operation = useMutation({
    mutationFn: async (task: () => Promise<unknown>) => task(),
    onMutate: () => setOperationError(null),
    onSuccess: () => { notifications.show({ title: 'Saved', message: 'Your knowledge base has been updated.', color: 'green' }); },
    onError: (error) => setOperationError(getApiErrorMessage(error)),
    onSettled: () => cache.invalidateQueries({ queryKey: rootKey }),
  });
  const chat = useMutation({
    mutationFn: (message: string) => service.chat(course!, message, conversationId),
    onSuccess: (data, message) => {
      setMessages((old) => [...old, { role: 'You', text: message }, { role: 'AskNarelle', text: data.answer }]);
      setConversationId(data.conversation_id); setQuestion('');
    },
  });
  const busy = operation.isPending || chat.isPending;
  const selectedCourse = courses.data?.find((item) => item.course_name === course);
  const filtered = courses.data?.filter((item) => `${item.course_name} ${item.course_display_name ?? ''}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  const error = courses.error || categories.error || documents.error;

  return (
    <Stack gap={22}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <h2>Knowledge Base</h2>
          <p>Manage the course materials AskNarelle uses to answer student questions.</p>
        </div>
        <div className="button-row">
          <Button variant="default" leftSection={<IconRefresh size={15} />} disabled={busy} loading={courses.isFetching} onClick={() => cache.invalidateQueries({ queryKey: rootKey })}>
            {courses.isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
          <Button leftSection={<IconPlus size={16} />} onClick={() => { operation.reset(); setOperationError(null); setCourseModal(true); }} disabled={busy}>Add course</Button>
        </div>
      </div>
      {error && <Alert color="red" title="Unable to load knowledge base">{getApiErrorMessage(error)}</Alert>}
      {operationError && <Alert color="red" title="Could not finish the operation">{operationError}</Alert>}
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Card withBorder><Text size="sm" c="dimmed">Your courses</Text><Title order={2}>{courses.isPending ? '—' : courses.data?.length ?? '—'}</Title></Card>
        <Card withBorder><Text size="sm" c="dimmed">Categories in selected course</Text><Title order={2}>{course && categories.data ? categories.data.length : '—'}</Title></Card>
        <Card withBorder><Text size="sm" c="dimmed">Documents in selected category</Text><Title order={2}>{category && documents.data ? documents.data.length : '—'}</Title></Card>
      </SimpleGrid>
      <Card withBorder padding="lg">
        <Group justify="space-between" mb="md"><Title order={3}>Course knowledge bases</Title><TextInput aria-label="Search courses" placeholder="Search courses" value={search} onChange={(event) => setSearch(event.currentTarget.value)} /></Group>
        {courses.isPending ? <Loader aria-label="Loading courses" /> : !courses.error && filtered.length === 0 ? <Text c="dimmed" py="xl" ta="center">{search ? 'No courses match your search.' : 'No courses yet. Add your first course to start building a chatbot knowledge base.'}</Text> : (
          <Table.ScrollContainer minWidth={600}><Table highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>Course code</Table.Th><Table.Th>Course name</Table.Th><Table.Th>Access</Table.Th><Table.Th>Created</Table.Th><Table.Th>Action</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{filtered.map((item) => <Table.Tr key={item.course_name} bg={course === item.course_name ? 'var(--mantine-color-blue-light)' : undefined}>
              <Table.Td fw={600}>{item.course_name}</Table.Td><Table.Td>{item.course_display_name || '—'}</Table.Td>
              <Table.Td><Badge variant="light">{item.user_type === 'root_user' ? 'Owner' : 'Shared'}</Badge></Table.Td>
              <Table.Td>{item.created_at ? new Date(item.created_at).toLocaleDateString('en-SG') : '—'}</Table.Td>
              <Table.Td><Button size="xs" variant={course === item.course_name ? 'filled' : 'light'} disabled={busy} onClick={() => { setCourse(item.course_name); setCategory(null); setFiles([]); setMessages([]); setConversationId(undefined); setQuestion(''); setOperationError(null); chat.reset(); }}>Manage</Button></Table.Td>
            </Table.Tr>)}</Table.Tbody>
          </Table></Table.ScrollContainer>
        )}
      </Card>
      {course && selectedCourse && <Card withBorder padding="lg"><Stack>
        <Group justify="space-between"><div><Text size="sm" c="dimmed">{course}</Text><Title order={3}>{selectedCourse.course_display_name || course}</Title></div><Badge variant="light">AskNarelle</Badge></Group>
        <Tabs defaultValue="materials"><Tabs.List><Tabs.Tab value="materials">Knowledge base</Tabs.Tab><Tabs.Tab value="preview">Chat preview</Tabs.Tab></Tabs.List>
          <Tabs.Panel value="materials" pt="lg"><Stack>
            <Group align="end"><Select label="Category" placeholder={categories.data?.length ? 'Select a category' : 'Create a category to organise materials'} data={categories.data?.map((item) => ({ value: item.domain, label: item.domain })) ?? []} value={category} onChange={(value) => { setCategory(value); setFiles([]); }} disabled={busy || categories.isPending} style={{ flex: 1 }} />
              <Button variant="light" disabled={busy} onClick={() => { setOperationError(null); setCategoryModal(true); }}>Add category</Button></Group>
            {categories.isPending && <Loader size="sm" aria-label="Loading categories" />}
            {category && <><FileInput label="Upload course documents" description="PDF, DOCX, PPTX or TXT. Up to 10 files, 20 MB per file and 50 MB combined." accept=".pdf,.docx,.pptx,.txt" multiple clearable value={files} onChange={setFiles} disabled={busy} />
              <Group><Button leftSection={<IconUpload size={16} />} disabled={!files.length || busy} loading={operation.isPending} onClick={() => {
                if (files.length > 10 || files.some((file) => !file.size || file.size > 20 * 1024 * 1024) || files.reduce((sum, file) => sum + file.size, 0) > 50 * 1024 * 1024) {
                  setOperationError('Choose up to 10 nonempty documents, 20 MB per file and 50 MB combined.'); return;
                }
                operation.mutate(async () => { await service.upload(course, category, files); setFiles([]); });
              }}>Upload and index</Button><Text size="sm" c="dimmed">Processing may take a few minutes.</Text></Group>
              {documents.isPending ? <Loader size="sm" aria-label="Loading documents" /> : documents.data?.length ? <Table.ScrollContainer minWidth={420}><Table>
                <Table.Thead><Table.Tr><Table.Th>Document</Table.Th><Table.Th>Uploaded</Table.Th><Table.Th>Search inclusion</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{documents.data.map((file) => <Table.Tr key={file._id}><Table.Td>{file.name}</Table.Td><Table.Td>{file.date_str || '—'}</Table.Td><Table.Td><Badge color={['yes', 'true'].includes(String(file.in_vector_store).toLowerCase()) ? 'green' : 'gray'}>{['yes', 'true'].includes(String(file.in_vector_store).toLowerCase()) ? 'Included' : 'Not included'}</Badge></Table.Td></Table.Tr>)}</Table.Tbody>
              </Table></Table.ScrollContainer> : !documents.error && <Text c="dimmed" ta="center" py="lg">No documents in this category yet.</Text>}
            </>}
            <Group justify="end"><Button variant="subtle" size="xs" disabled={busy} onClick={() => operation.mutate(() => service.repairIndex(course))}>Repair search index</Button></Group>
          </Stack></Tabs.Panel>
          <Tabs.Panel value="preview" pt="lg"><Stack>
            <Text c="dimmed" size="sm">Test answers against this course’s indexed documents. Preview conversations are saved in AskNarelle under your account.</Text>
            <Stack aria-live="polite">{messages.length === 0 && <Text ta="center" c="dimmed" py="lg">Upload and index course materials, then ask a question to test your chatbot.</Text>}{messages.map((message, index) => <Card key={index} withBorder bg={message.role === 'You' ? 'var(--mantine-color-blue-light)' : undefined}><Text fw={600} size="sm" mb="xs">{message.role}</Text><Text style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{message.text}</Text></Card>)}</Stack>
            {chat.error && <Alert color="red">{getApiErrorMessage(chat.error)}</Alert>}
            <Textarea label="Test question" placeholder="What does this course say about SQL joins?" value={question} onChange={(event) => setQuestion(event.currentTarget.value)} minRows={3} disabled={busy} maxLength={10000} />
            <Group justify="space-between"><Button variant="default" disabled={busy || !messages.length} onClick={() => { setMessages([]); setConversationId(undefined); chat.reset(); }}>New conversation</Button><Button loading={chat.isPending} disabled={busy || !question.trim()} onClick={() => chat.mutate(question.trim())}>Send question</Button></Group>
          </Stack></Tabs.Panel>
        </Tabs>
      </Stack></Card>}
      <Modal opened={courseModal} onClose={() => !busy && setCourseModal(false)} title="Add course knowledge base" closeOnClickOutside={!busy} closeOnEscape={!busy} withCloseButton={!busy}>
        <form onSubmit={(event) => { event.preventDefault(); operation.mutate(async () => { await service.createCourse({ code, name: name.trim(), description: description.trim() }); setCourseModal(false); setCode(''); setName(''); setDescription(''); }); }}>
          <Stack><TextInput label="Course code" description="3–63 lowercase letters, numbers or hyphens; start and end with a letter or number." placeholder="sc2207" required pattern="[a-z0-9][a-z0-9-]{1,61}[a-z0-9]" value={code} onChange={(event) => setCode(event.currentTarget.value)} disabled={busy} />
            <TextInput label="Course name" required maxLength={150} value={name} onChange={(event) => setName(event.currentTarget.value)} disabled={busy} />
            <Textarea label="Description" maxLength={2000} value={description} onChange={(event) => setDescription(event.currentTarget.value)} disabled={busy} />
            {operationError && <Alert color="red">{operationError}</Alert>}<Button type="submit" loading={operation.isPending} disabled={!name.trim()}>Create course</Button></Stack>
        </form>
      </Modal>
      <Modal opened={categoryModal} onClose={() => !busy && setCategoryModal(false)} title="Add category" closeOnClickOutside={!busy} closeOnEscape={!busy} withCloseButton={!busy}>
        <form onSubmit={(event) => { event.preventDefault(); operation.mutate(async () => { await service.createCategory(course!, categoryName); setCategory(categoryName); setCategoryModal(false); setCategoryName(''); }); }}>
          <Stack><TextInput label="Category name" description="Lowercase letters and numbers, e.g. lecture01" required pattern="[a-z0-9]{1,63}" value={categoryName} onChange={(event) => setCategoryName(event.currentTarget.value)} disabled={busy} />
            {operationError && <Alert color="red">{operationError}</Alert>}<Button type="submit" loading={operation.isPending}>Create category</Button></Stack>
        </form>
      </Modal>
    </Stack>
  );
}

export default function ChatbotManagementPage() {
  return <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}><DashboardLayout><ChatbotManagementShell><Management /></ChatbotManagementShell></DashboardLayout></ProtectedRoute>;
}
