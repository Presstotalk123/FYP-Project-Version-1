'use client';

import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { LabWizardShell } from '@/components/admin/LabWizardShell';
import { UserRole } from '@/types/user.types';

export default function LabWizardPage() {
  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <LabWizardShell title="Create New Lab" />
    </ProtectedRoute>
  );
}
