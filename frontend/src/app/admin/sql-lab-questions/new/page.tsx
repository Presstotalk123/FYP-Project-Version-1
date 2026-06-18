// frontend/src/app/admin/sql-lab-questions/new/page.tsx
'use client';

import { Container } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { SqlLabQuestionForm } from '@/components/admin/SqlLabQuestionForm';

export default function NewSqlLabQuestionPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Container size="lg">
          <SqlLabQuestionForm />
        </Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
