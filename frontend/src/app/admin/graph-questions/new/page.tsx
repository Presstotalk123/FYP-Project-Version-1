// frontend/src/app/admin/graph-questions/new/page.tsx
'use client';

import { Container } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { GraphQuestionForm } from '@/components/admin/GraphQuestionForm';

export default function NewGraphQuestionPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Container size="lg">
          <GraphQuestionForm />
        </Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
