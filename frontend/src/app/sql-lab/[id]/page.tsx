'use client';

import { useParams, useRouter } from 'next/navigation';
import { Anchor, Box } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { sqlLabQuestionService } from '@/services/sqlLabQuestion.service';
import { SqlLabSolver } from '@/components/lab/SqlLabSolver';

function SqlLabPracticeView({ id }: { id: number }) {
  const router = useRouter();
  return (
    <Box p="md">
      <Anchor onClick={() => router.push('/problems')} c="dimmed" size="sm"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer', marginBottom: 8 }}>
        <IconArrowLeft size={14} /> Back to problems
      </Anchor>
      <SqlLabSolver
        loadQuestion={() => sqlLabQuestionService.loadForSolver(id)}
        run={(query) => sqlLabQuestionService.run(id, query)}
        submit={(query, taskId) => sqlLabQuestionService.submit(id, query, taskId)}
        getDatabase={() => sqlLabQuestionService.database(id)}
        reset={() => sqlLabQuestionService.reset(id)}
      />
    </Box>
  );
}

export default function SqlLabPracticePage() {
  const params = useParams<{ id: string }>();
  return (
    <ProtectedRoute>
      <SqlLabPracticeView id={Number(params.id)} />
    </ProtectedRoute>
  );
}
