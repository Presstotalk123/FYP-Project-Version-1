'use client';

import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { LeaderboardView } from '@/components/leaderboard/LeaderboardView';
import { UserRole } from '@/types/user.types';

export default function StaffLeaderboardPage() {
  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <LeaderboardView showEmail />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
