'use client';

import { useRouter } from 'next/navigation';
import { Alert } from '@mantine/core';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { NormalizationQuestionForm } from './NormalizationQuestionForm';
import styles from './NormalizationStaff.module.css';

export function NormalizationQuestionEditor({ questionId }: { questionId?: number }) {
  const router = useRouter();
  const returnToProblems = () => router.push('/admin/problems');
  const invalidId = questionId !== undefined && (!Number.isSafeInteger(questionId) || questionId <= 0);

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div className={styles.editorPage}>
          <header className="page-head"><div>
            <h1 className={styles.pageTitle}>
              {questionId === undefined ? 'Create Normalization Question' : 'Edit Normalization Question'}
            </h1>
            <p>Prepare the problem, reference dependencies, and student feedback.</p>
          </div></header>
          {invalidId ? <Alert color="red">Invalid question ID</Alert> : (
            <NormalizationQuestionForm key={questionId ?? 'new'} questionId={questionId}
              onSaved={returnToProblems} onCancel={returnToProblems} />
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
