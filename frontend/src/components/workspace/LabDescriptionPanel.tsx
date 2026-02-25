'use client';

import { Stack, Title, Text, Badge, Group, Divider, Code, Button } from '@mantine/core';
import { IconRefresh } from '@tabler/icons-react';
import { LabDetail } from '@/types/lab.types';

interface LabDescriptionPanelProps {
  lab: LabDetail | null;
  sessionId: number | null;
}

export function LabDescriptionPanel({ lab, sessionId }: LabDescriptionPanelProps) {
  if (!lab) {
    return (
      <Stack align="center" justify="center" p="md" style={{ height: '100%' }}>
        <Text c="dimmed">Loading lab...</Text>
      </Stack>
    );
  }

  return (
    <Stack gap="md" p="md" style={{ height: '100%', overflow: 'auto' }}>
      <Group justify="space-between" align="flex-start">
        <Title order={3}>{lab.title}</Title>
        {sessionId && <Badge color="green">Active Session</Badge>}
      </Group>

      <Text size="sm" c="dimmed">
        {lab.description}
      </Text>

      <Divider />

      <div>
        <Text size="sm" fw={500} mb="xs">
          Database Schema
        </Text>
        <Code block style={{ fontSize: '12px', maxHeight: '200px', overflow: 'auto' }}>
          {lab.schema_sql}
        </Code>
      </div>

      <Divider />

      <div>
        <Text size="sm" fw={500} mb="xs">
          Sample Data
        </Text>
        <Code block style={{ fontSize: '12px', maxHeight: '200px', overflow: 'auto' }}>
          {lab.sample_data_sql}
        </Code>
      </div>
    </Stack>
  );
}
