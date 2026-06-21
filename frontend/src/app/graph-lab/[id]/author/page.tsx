'use client';
import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { QuestionAuthorWorkspace } from '@/components/question/QuestionAuthorWorkspace';
import { graphAuthorConfig } from '@/config/questionAuthorConfigs';

export default function AuthorGraphLabPage() {
  const id = parseInt(useParams().id as string, 10);
  return (
    <ProtectedRoute>
      <DashboardLayout><QuestionAuthorWorkspace id={id} config={graphAuthorConfig} /></DashboardLayout>
    </ProtectedRoute>
  );
}
