'use client';

import { Badge, Code, Divider, Stack, Text, Title } from '@mantine/core';
import { QuestionDetail } from '@/types/question.types';

interface QuestionPanelProps {
  question: QuestionDetail;
}

const difficultyColors: Record<string, string> = {
  easy: 'green',
  medium: 'yellow',
  hard: 'red',
};

export function QuestionPanel({ question }: QuestionPanelProps) {
  return (
    <Stack gap="md" p="md" style={{ height: '100%', overflow: 'auto' }}>
      <div>
        <Title order={3}>{question.title}</Title>
        <Badge
          color={difficultyColors[question.difficulty]}
          variant="light"
          mt="xs"
        >
          {question.difficulty.charAt(0).toUpperCase() + question.difficulty.slice(1)}
        </Badge>
      </div>

      <div>
        <Text size="sm">{question.description}</Text>
      </div>

      <Divider />

      <div>
        <Title order={4} size="h6" mb="xs">
          Database Schema
        </Title>
        <Code block style={{ fontSize: '12px' }}>
          {question.schema_sql}
        </Code>
      </div>

      <Divider />

      <div>
        <Title order={4} size="h6" mb="xs">
          Sample Data
        </Title>
        <Code block style={{ fontSize: '12px' }}>
          {question.sample_data_sql}
        </Code>
      </div>
    </Stack>
  );
}
