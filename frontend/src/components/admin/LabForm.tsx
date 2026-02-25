'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Button,
  TextInput,
  Textarea,
  Stack,
  Group,
  Title,
  Alert,
  Text,
  Box,
} from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import Editor from '@monaco-editor/react';
import { LabDetail } from '@/types/lab.types';
import { labService } from '@/services/lab.service';

interface LabFormProps {
  lab?: LabDetail;
  isEdit?: boolean;
}

export function LabForm({ lab, isEdit = false }: LabFormProps) {
  const router = useRouter();

  // Form state
  const [title, setTitle] = useState(lab?.title || '');
  const [description, setDescription] = useState(lab?.description || '');
  const [schemaSql, setSchemaSql] = useState(lab?.schema_sql || '');
  const [sampleDataSql, setSampleDataSql] = useState(lab?.sample_data_sql || '');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!title.trim()) {
      setError('Title is required');
      return;
    }
    if (!description.trim()) {
      setError('Description is required');
      return;
    }
    if (!schemaSql.trim()) {
      setError('Schema SQL is required');
      return;
    }
    if (!sampleDataSql.trim()) {
      setError('Sample Data SQL is required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = {
        title,
        description,
        schema_sql: schemaSql,
        sample_data_sql: sampleDataSql,
      };

      if (isEdit && lab) {
        // Update existing lab
        await labService.updateLab(lab.id, payload);
        notifications.show({
          title: 'Success',
          message: 'Lab updated successfully',
          color: 'green',
        });
      } else {
        // Create new lab
        await labService.createLab(payload);
        notifications.show({
          title: 'Success',
          message: 'Lab created successfully',
          color: 'green',
        });
      }

      router.push('/admin/labs');
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      const errorMessage =
        error.response?.data?.detail || `Failed to ${isEdit ? 'update' : 'create'} lab`;
      setError(errorMessage);
      notifications.show({
        title: 'Error',
        message: errorMessage,
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Stack gap="md">
        <Title order={2}>{isEdit ? 'Edit Lab' : 'Create New Lab'}</Title>

        {error && (
          <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
            {error}
          </Alert>
        )}

        {isEdit && lab && lab.is_running && (
          <Alert icon={<IconAlertCircle size={16} />} color="yellow" title="Lab is Running">
            This lab is currently running. Stop the lab before editing.
          </Alert>
        )}

        <TextInput
          label="Title"
          placeholder="Enter lab title"
          required
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          disabled={loading || (isEdit && lab?.is_running)}
        />

        <Textarea
          label="Description"
          placeholder="Enter lab description"
          required
          minRows={4}
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
          disabled={loading || (isEdit && lab?.is_running)}
        />

        <Box>
          <Text size="sm" fw={500} mb="xs">
            Schema SQL (CREATE TABLE statements) <span style={{ color: 'red' }}>*</span>
          </Text>
          <Box
            style={{
              border: '1px solid var(--mantine-color-gray-3)',
              borderRadius: '8px',
              overflow: 'hidden',
            }}
          >
            <Editor
              height="200px"
              language="sql"
              theme="vs-dark"
              value={schemaSql}
              onChange={(value) => setSchemaSql(value || '')}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                readOnly: loading || (isEdit && lab?.is_running),
              }}
            />
          </Box>
        </Box>

        <Box>
          <Text size="sm" fw={500} mb="xs">
            Sample Data SQL (INSERT statements) <span style={{ color: 'red' }}>*</span>
          </Text>
          <Box
            style={{
              border: '1px solid var(--mantine-color-gray-3)',
              borderRadius: '8px',
              overflow: 'hidden',
            }}
          >
            <Editor
              height="200px"
              language="sql"
              theme="vs-dark"
              value={sampleDataSql}
              onChange={(value) => setSampleDataSql(value || '')}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                readOnly: loading || (isEdit && lab?.is_running),
              }}
            />
          </Box>
        </Box>

        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => router.push('/admin/labs')}>
            Cancel
          </Button>
          <Button
            type="submit"
            loading={loading}
            disabled={isEdit && lab?.is_running}
          >
            {isEdit ? 'Update Lab' : 'Create Lab'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
