'use client';

import { Stack, Group, Button, Badge, Box } from '@mantine/core';
import { IconPlayerPlay, IconTrash } from '@tabler/icons-react';
import Editor from '@monaco-editor/react';

interface LabEditorPanelProps {
  query: string;
  onQueryChange: (query: string) => void;
  onExecute: () => void;
  onClear: () => void;
  isExecuting: boolean;
  executionTime: number | null;
}

export function LabEditorPanel({
  query,
  onQueryChange,
  onExecute,
  onClear,
  isExecuting,
  executionTime,
}: LabEditorPanelProps) {
  return (
    <Stack gap="md" p="md" style={{ height: '100%' }}>
      <Group justify="space-between" wrap="nowrap">
        <Group gap="xs" wrap="nowrap">
          <Button
            leftSection={<IconPlayerPlay size={16} />}
            onClick={onExecute}
            loading={isExecuting}
            color="blue"
            size="sm"
          >
            Run Query
          </Button>
          <Button
            leftSection={<IconTrash size={16} />}
            onClick={onClear}
            variant="light"
            color="gray"
            size="sm"
          >
            Clear
          </Button>
        </Group>
        {executionTime !== null && (
          <Badge color="gray" size="sm">
            {executionTime.toFixed(2)}ms
          </Badge>
        )}
      </Group>

      <Box style={{ flex: 1, overflow: 'hidden' }}>
        <Editor
          height="100%"
          language="sql"
          theme="vs-dark"
          value={query}
          onChange={(value) => onQueryChange(value || '')}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
          }}
        />
      </Box>
    </Stack>
  );
}
