'use client';

import { useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Badge, Card, Group, Loader, Select, Stack, Table, Text, TextInput } from '@mantine/core';
import { IconRefresh } from '@tabler/icons-react';
import { useAuth } from '@/contexts/AuthContext';
import { chatbotManagementService as service } from '@/services/chatbot-management.service';
import { getApiErrorMessage } from '@/utils/api-error';
import { ChatbotDashboard } from './ChatbotDashboard';
import { AkelaButton as Button } from './AkelaButton';
import styles from './ChatbotManagementShell.module.css';

type Section = 'home' | 'knowledge-base' | 'activity-log';
const sections = [
  { key: 'home', label: 'Dashboard' },
  { key: 'knowledge-base', label: 'Knowledge Base' },
  { key: 'activity-log', label: 'Activity Log' },
] as const;


function ActivityLog() {
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const [action, setAction] = useState<string | null>(null);
  const query = useQuery({ queryKey: ['chatbot-management', user?.id, 'activities'], queryFn: service.activities });
  const actions = [...new Set(query.data?.map((item) => item.action).filter(Boolean) ?? [])].sort();
  // Legacy AskNarelle repeats the course ID in activity._id. Assign keys before
  // filtering/sorting so distinct events remain visible and keep their identity.
  const rows = (query.data ?? []).map((item, sourceIndex) => ({
    ...item, rowKey: JSON.stringify([item._id, sourceIndex]),
  })).filter((item) => (!action || item.action === action) &&
    [item.username, item.course_name, item.domain, item.file, item.action, item.date_str].join(' ').toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => `${b.date_str} ${b.time_str}`.localeCompare(`${a.date_str} ${a.time_str}`));
  const display = (value: string) => !value || value === 'null' ? '—' : value;
  return (
    <Stack gap={22}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div><h2>Activity Log</h2><p>Review changes to your AskNarelle course materials.</p></div>
        <div className="button-row"><Button variant="default" leftSection={<IconRefresh size={15} />} loading={query.isFetching} onClick={() => query.refetch()}>{query.isFetching ? 'Refreshing…' : 'Refresh'}</Button></div>
      </div>
      {query.error && <Alert color="red" title="Unable to load activity log">{getApiErrorMessage(query.error)}</Alert>}
      <Group align="end"><TextInput label="Search activity" placeholder="User, course, category or file" value={search} onChange={(event) => setSearch(event.currentTarget.value)} style={{ flex: 1 }} />
        <Select label="Action" placeholder="All actions" clearable data={actions} value={action} onChange={setAction} /></Group>
      {query.isPending ? <Loader aria-label="Loading activity log" /> : !query.error && <Card withBorder pt={3} pb={3}>
        {!rows.length ? <Text c="dimmed" py="xl" ta="center">{search || action ? 'No activities match your filters.' : 'No activity recorded yet.'}</Text> : (
          <Table.ScrollContainer minWidth={800}><Table striped highlightOnHover verticalSpacing="md">
            <Table.Thead><Table.Tr>{['User', 'Course', 'Category', 'File', 'Action', 'Date', 'Time'].map((label) => <Table.Th key={label}>{label}</Table.Th>)}</Table.Tr></Table.Thead>
            <Table.Tbody>{rows.map((item) => <Table.Tr key={item.rowKey}>
              <Table.Td><span className="pii">{display(item.username)}</span></Table.Td><Table.Td>{display(item.course_name)}</Table.Td>
              <Table.Td>{display(item.domain)}</Table.Td><Table.Td>{display(item.file)}</Table.Td>
              <Table.Td><Badge variant="light">{display(item.action)}</Badge></Table.Td><Table.Td>{display(item.date_str)}</Table.Td><Table.Td>{display(item.time_str)}</Table.Td>
            </Table.Tr>)}</Table.Tbody>
          </Table></Table.ScrollContainer>
        )}
      </Card>}
    </Stack>
  );
}

export function ChatbotManagementShell({ children }: { children: ReactNode }) {
  const [section, setSection] = useState<Section>('home');
  return (
    <div className={styles.layout}>
      <nav className={styles.sidebar} aria-label="AskNarelle navigation">
        <span className={styles.label}>Chatbot Management</span>
        <div className={styles.links}>{sections.map(({ key, label }) => (
          <button key={key} className={styles.link} aria-current={section === key ? 'page' : undefined} aria-controls={`asknarelle-${key}`} onClick={() => setSection(key)}>
            <span>{label}</span>
          </button>
        ))}</div>
      </nav>
      <div className={styles.content}>
        {section === 'home' && <section id="asknarelle-home" aria-label="Home"><ChatbotDashboard /></section>}
        <section id="asknarelle-knowledge-base" aria-label="Knowledge Base" hidden={section !== 'knowledge-base'}>{children}</section>
        {section === 'activity-log' && <section id="asknarelle-activity-log" aria-label="Activity Log"><ActivityLog /></section>}
      </div>
    </div>
  );
}
