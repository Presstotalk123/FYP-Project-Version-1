'use client';
import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { QuestionAuthorWorkspace } from '@/components/question/QuestionAuthorWorkspace';
import { sqlLabAuthorConfig } from '@/config/questionAuthorConfigs';

export default function AuthorSqlLabPage() {
  const id = parseInt(useParams().id as string, 10);
  return (
    <ProtectedRoute>
      <DashboardLayout><QuestionAuthorWorkspace id={id} config={sqlLabAuthorConfig} /></DashboardLayout>
    </ProtectedRoute>
  );
}
