'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Button,
  TextInput,
  Textarea,
  Select,
  Stack,
  Group,
  Title,
  Alert,
} from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import Editor from '@monaco-editor/react';
import { QuestionDetail, Difficulty } from '@/types/question.types';
import api from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api.config';

interface QuestionFormProps {
  question?: QuestionDetail;
  isEdit?: boolean;
}

export function QuestionForm({ question, isEdit = false }: QuestionFormProps) {
  const router = useRouter();

  // Form state
  const [title, setTitle] = useState(question?.title || '');
  const [description, setDescription] = useState(question?.description || '');
  const [difficulty, setDifficulty] = useState<string>(question?.difficulty || 'easy');
  const [schemaSql, setSchemaSql] = useState(question?.schema_sql || '');
  const [sampleDataSql, setSampleDataSql] = useState(question?.sample_data_sql || '');
  const [correctAnswerQuery, setCorrectAnswerQuery] = useState('');

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
    if (!isEdit && !correctAnswerQuery.trim()) {
      setError('Correct Answer Query is required for new questions');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload: any = {
        title,
        description,
        difficulty: difficulty as Difficulty,
        schema_sql: schemaSql,
        sample_data_sql: sampleDataSql,
      };

      // Only include correct_answer_query for new questions
      if (!isEdit) {
        payload.correct_answer_query = correctAnswerQuery;
      }

      if (isEdit && question) {
        // Update existing question
        await api.put(API_ENDPOINTS.QUESTIONS.DETAIL(question.id), payload);
        notifications.show({
          title: 'Success',
          message: 'Question updated successfully',
          color: 'green',
        });
      } else {
        // Create new question
        await api.post(API_ENDPOINTS.QUESTIONS.BASE, payload);
        notifications.show({
          title: 'Success',
          message: 'Question created successfully',
          color: 'green',
        });
      }

      router.push('/admin/questions');
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      const errorMessage = error.response?.data?.detail ||
        `Failed to ${isEdit ? 'update' : 'create'} question`;
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
        <Title order={2}>{isEdit ? 'Edit Question' : 'Create New Question'}</Title>

        {error && (
          <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
            {error}
          </Alert>
        )}

        <TextInput
          label="Question Title"
          placeholder="Enter question title"
          required
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
        />

        <Textarea
          label="Description"
          placeholder="Enter question description"
          required
          minRows={3}
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
        />

        <Select
          label="Difficulty"
          placeholder="Select difficulty"
          required
          data={[
            { label: 'Easy', value: 'easy' },
            { label: 'Medium', value: 'medium' },
            { label: 'Hard', value: 'hard' },
          ]}
          value={difficulty}
          onChange={(value) => setDifficulty(value || 'easy')}
        />

        <div>
          <Title order={5} mb="xs">Schema SQL</Title>
          <div style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: '8px', overflow: 'hidden' }}>
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
              }}
            />
          </div>
        </div>

        <div>
          <Title order={5} mb="xs">Sample Data SQL</Title>
          <div style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: '8px', overflow: 'hidden' }}>
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
              }}
            />
          </div>
        </div>

        {!isEdit && (
          <div>
            <Title order={5} mb="xs">Correct Answer Query</Title>
            <div style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: '8px', overflow: 'hidden' }}>
              <Editor
                height="150px"
                language="sql"
                theme="vs-dark"
                value={correctAnswerQuery}
                onChange={(value) => setCorrectAnswerQuery(value || '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: 'on',
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          </div>
        )}

        <Group justify="flex-end" mt="md">
          <Button
            variant="default"
            onClick={() => router.push('/admin/questions')}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button type="submit" loading={loading}>
            {isEdit ? 'Update Question' : 'Create Question'}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
