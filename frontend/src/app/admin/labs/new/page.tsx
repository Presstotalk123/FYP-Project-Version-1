'use client';

import { Container } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { LabForm } from '@/components/admin/LabForm';
import { UserRole } from '@/types/user.types';

export default function NewLabPage() {
  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <Container size="lg">
          <LabForm />
        </Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
