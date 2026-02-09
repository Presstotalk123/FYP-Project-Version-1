'use client';

import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { SqlWorkspace } from '@/components/workspace/SqlWorkspace';
import { UserRole } from '@/types/user.types';

export default function WorkspacePage() {
  const params = useParams();
  const questionId = parseInt(params.id as string);

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <SqlWorkspace questionId={questionId} />
    </ProtectedRoute>
  );
}
