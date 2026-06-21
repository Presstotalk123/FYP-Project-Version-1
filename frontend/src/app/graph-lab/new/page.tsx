'use client';
import { Container } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { QuestionMetaForm } from '@/components/question/QuestionMetaForm';
import { graphAuthorConfig } from '@/config/questionAuthorConfigs';

export default function NewGraphLabPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Container size="lg"><QuestionMetaForm config={graphAuthorConfig} kindLabel="Graph question" /></Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
