'use client';

import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { QuestionForm } from '@/components/admin/QuestionForm';
import { UserRole } from '@/types/user.types';

export default function NewQuestionPage() {
  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          <div className="card" style={{ padding: 28 }}>
            <h3 style={{ margin: '0 0 20px', fontSize: 20 }}>Create New Question</h3>
            <QuestionForm />
          </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
