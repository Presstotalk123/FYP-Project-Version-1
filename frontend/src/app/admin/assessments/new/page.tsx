'use client';

import { Title, Stack } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { AssessmentForm } from '@/components/admin/AssessmentForm';
import { UserRole } from '@/types/user.types';

export default function NewAssessmentPage() {
  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Stack gap="md">
          <Title order={2}>Create Assessment</Title>
          <AssessmentForm mode="create" />
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
