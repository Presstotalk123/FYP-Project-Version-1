'use client';

import { useParams, useRouter } from 'next/navigation';
import { Anchor, Box } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { graphQuestionService } from '@/services/graphQuestion.service';
import { SqlLabSolver } from '@/components/lab/SqlLabSolver';

function GraphLabPracticeView({ id }: { id: number }) {
  const router = useRouter();
  return (
    <Box p="md">
      <Anchor onClick={() => router.push('/problems')} c="dimmed" size="sm"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer', marginBottom: 8 }}>
        <IconArrowLeft size={14} /> Back to problems
      </Anchor>
      <SqlLabSolver
        key={id}
        editorLanguage="cypher"
        loadQuestion={() => graphQuestionService.loadForSolver(id)}
        run={(query) => graphQuestionService.run(id, query)}
        submit={(query, taskId) => graphQuestionService.submit(id, query, taskId)}
        getDatabase={() => graphQuestionService.database(id)}
        reset={() => graphQuestionService.reset(id)}
      />
    </Box>
  );
}

export default function GraphLabPracticePage() {
  const params = useParams<{ id: string }>();
  return (
    <ProtectedRoute>
      <GraphLabPracticeView id={Number(params.id)} />
    </ProtectedRoute>
  );
}
