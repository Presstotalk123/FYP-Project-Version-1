'use client';

import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { LabWorkspace } from '@/components/workspace/LabWorkspace';

export default function AdminLabWorkspacePage() {
  const params = useParams();
  const labId = parseInt(params.id as string);

  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <LabWorkspace labId={labId} isStaffMode={true} />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
