'use client';

import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { UnifiedLabWorkspace } from '@/components/lab/UnifiedLabWorkspace';

export default function LabWorkspacePage() {
  const params = useParams<{ id: string }>();
  return (
    <ProtectedRoute>
      <UnifiedLabWorkspace labId={Number(params.id)} />
    </ProtectedRoute>
  );
}
