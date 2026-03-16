'use client';

import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { LabWorkspace } from '@/components/workspace/LabWorkspace';

export default function LabReviewPage() {
  const params = useParams();
  const labId = parseInt(params.id as string);
  const studentId = parseInt(params.studentId as string);

  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <LabWorkspace
          labId={labId}
          isStaffMode={true}
          reviewMode={true}
          reviewStudentId={studentId}
        />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
