'use client';
import { Container } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { QuestionMetaForm } from '@/components/question/QuestionMetaForm';
import { sqlLabAuthorConfig } from '@/config/questionAuthorConfigs';

export default function NewSqlLabPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Container size="lg"><QuestionMetaForm config={sqlLabAuthorConfig} kindLabel="SQL-lab question" /></Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
