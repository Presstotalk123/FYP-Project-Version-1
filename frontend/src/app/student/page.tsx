'use client';

import { Title, Text } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';

export default function StudentDashboard() {
  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <Title order={2}>Student Dashboard</Title>
        <Text mt="sm">Welcome to the SQL Learning Platform!</Text>
        <Text mt="xs">Questions list will be displayed here (Phase 5).</Text>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
