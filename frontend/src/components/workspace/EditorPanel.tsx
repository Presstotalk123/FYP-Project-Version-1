'use client';

import { Button, Group, Stack, Text } from '@mantine/core';
import { IconPlayerPlay, IconTrash, IconCheck } from '@tabler/icons-react';
import dynamic from 'next/dynamic';

const Editor = dynamic(() => import('@monaco-editor/react'), { ssr: false });

interface EditorPanelProps {
  query: string;
  onQueryChange: (value: string) => void;
  onExecute: () => void;
  onClear: () => void;
  isExecuting: boolean;
  executionTime: number | null;
  // Lab mode only: when provided, a Submit button grades the lab item.
  onSubmit?: () => void;
  isSubmitting?: boolean;
}

export function EditorPanel({
  query,
  onQueryChange,
  onExecute,
  onClear,
  isExecuting,
  executionTime,
  onSubmit,
  isSubmitting,
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
          {onSubmit && (
            <Button
              color="green"
              leftSection={<IconCheck size={16} />}
              onClick={onSubmit}
              loading={isSubmitting}
              disabled={isExecuting}
            >
              Submit
            </Button>
          )}
          <Button
            variant="default"
            leftSection={<IconTrash size={16} />}
            onClick={onClear}
            disabled={isExecuting || isSubmitting}
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
