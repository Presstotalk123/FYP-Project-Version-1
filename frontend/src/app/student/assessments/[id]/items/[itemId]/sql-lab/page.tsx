'use client';

import { useEffect } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { LabWorkspace } from '@/components/workspace/LabWorkspace';
import { UserRole } from '@/types/user.types';
import { studentAssessmentService } from '@/services/studentAssessment.service';

export default function AssessmentSqlLabPage() {
  const params = useParams();
  const searchParams = useSearchParams();

  const assessmentId = Number(params.id);
  const itemId = Number(params.itemId);
  const resourceId = Number(searchParams.get('resourceId'));
  const weight = Number(searchParams.get('weight')) || undefined;
  const backUrl = `/student/assessments/${assessmentId}/overview`;

  useEffect(() => {
    if (assessmentId && itemId) {
      studentAssessmentService.visitItem(assessmentId, itemId).catch(() => {
        // Non-critical — ignore errors
      });
    }
  }, [assessmentId, itemId]);

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <LabWorkspace labId={resourceId} backUrl={backUrl} inAssessment weight={weight} />
    </ProtectedRoute>
  );
}
