'use client';

import { Suspense } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { Alert, Loader } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { SqlWorkspace } from '@/components/workspace/SqlWorkspace';
import { NormalizationWorkspace } from '@/components/normalization/NormalizationWorkspace';
import { UserRole } from '@/types/user.types';

function Workspace() {
  const params = useParams();
  const search = useSearchParams();
  const questionId = Number(params.id);
  const type = search.get('type') || 'sql';
  return <ProtectedRoute requiredRole={UserRole.STUDENT}>
    {type === 'sql' ? <SqlWorkspace questionId={questionId} /> : type === 'normalization'
      ? <DashboardLayout><NormalizationWorkspace questionId={questionId} /></DashboardLayout>
      : <Alert color="red">Unsupported question type.</Alert>}
  </ProtectedRoute>;
}
export default function WorkspacePage() {
  return <Suspense fallback={<Loader />}><Workspace /></Suspense>;
}
