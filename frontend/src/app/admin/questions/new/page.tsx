'use client';

import { Container } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { QuestionForm } from '@/components/admin/QuestionForm';

export default function NewQuestionPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Container size="lg">
          <QuestionForm />
        </Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
