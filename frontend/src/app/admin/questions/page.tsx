'use client';

import { Title, Text } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';

export default function AdminQuestions() {
  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <Title order={2}>Manage Questions</Title>
        <Text mt="sm">
          Question management interface will be implemented in Phase 6.
        </Text>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
