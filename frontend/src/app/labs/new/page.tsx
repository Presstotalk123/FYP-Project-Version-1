'use client';

import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { UserRole } from '@/types/user.types';
import { LabBuilder } from '@/components/lab/LabBuilder';

export default function NewLabPage() {
  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <LabBuilder />
    </ProtectedRoute>
  );
}
