'use client';

import { Button, Group, Stack, Text } from '@mantine/core';
import { IconPlayerPlay, IconTrash } from '@tabler/icons-react';
import Editor from '@monaco-editor/react';

interface EditorPanelProps {
  query: string;
  onQueryChange: (value: string) => void;
  onExecute: () => void;
  onClear: () => void;
  isExecuting: boolean;
  executionTime: number | null;
}

export function EditorPanel({
  query,
  onQueryChange,
  onExecute,
  onClear,
  isExecuting,
  executionTime,
}: EditorPanelProps) {
  return (
    <Stack gap="md" p="md" style={{ height: '100%' }}>
      <Group justify="space-between">
        <Group gap="xs">
          <Button
            leftSection={<IconPlayerPlay size={16} />}
            onClick={onExecute}
            loading={isExecuting}
          >
            Run Query
          </Button>
          <Button
            variant="default"
            leftSection={<IconTrash size={16} />}
            onClick={onClear}
            disabled={isExecuting}
          >
            Clear
          </Button>
        </Group>
        {executionTime !== null && (
          <Text size="sm" c="dimmed">
            Executed in {executionTime.toFixed(2)}ms
          </Text>
        )}
      </Group>

      <div style={{ flex: 1, border: '1px solid var(--mantine-color-gray-3)', borderRadius: '8px', overflow: 'hidden' }}>
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
      </div>
    </Stack>
  );
}
