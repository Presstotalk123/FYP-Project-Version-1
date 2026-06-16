'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { LabWizardShell } from '@/components/admin/LabWizardShell';
import { UserRole } from '@/types/user.types';

function LabWizardPageContent() {
  const searchParams = useSearchParams();
  const labType: 'sql' | 'graph' =
    searchParams.get('type') === 'graph' ? 'graph' : 'sql';
  const title = labType === 'graph' ? 'Create Graph Lab' : 'Create New Lab';

  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <LabWizardShell title={title} labType={labType} />
    </ProtectedRoute>
  );
}

export default function LabWizardPage() {
  return (
    <Suspense>
      <LabWizardPageContent />
    </Suspense>
  );
}
