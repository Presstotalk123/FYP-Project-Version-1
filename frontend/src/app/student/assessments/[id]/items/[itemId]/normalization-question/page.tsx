'use client';

import { useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { AssessmentTimer } from '@/components/assessment/AssessmentTimer';
import { QuestionNavigator } from '@/components/assessment/QuestionNavigator';
import { QuestionWeightBadge } from '@/components/assessment/QuestionWeightBadge';
import { NormalizationWorkspace } from '@/components/normalization/NormalizationWorkspace';
import { useWarnBeforeUnload } from '@/hooks/use-warn-before-unload';
import { useBlockBrowserBack } from '@/hooks/use-block-browser-back';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { UserRole } from '@/types/user.types';

export default function AssessmentNormalizationPage() {
  const params = useParams();
  const search = useSearchParams();
  const router = useRouter();
  const assessmentId = Number(params.id);
  const itemId = Number(params.itemId);
  const resourceId = Number(search.get('resourceId'));
  const weight = Number(search.get('weight')) || undefined;
  useWarnBeforeUnload(true);
  useBlockBrowserBack(true);
  useEffect(() => { if (assessmentId && itemId) void studentAssessmentService.visitItem(assessmentId, itemId).catch(() => {}); }, [assessmentId, itemId]);
  return <ProtectedRoute requiredRole={UserRole.STUDENT}>
    <div style={{ padding: 16 }}>
      <div className="button-row"><AssessmentTimer /><QuestionWeightBadge weight={weight} />
        <button className="btn btn-secondary" onClick={() => router.push(`/student/assessments/${assessmentId}/overview`)}>Save and Exit</button>
      </div>
      <QuestionNavigator />
      <NormalizationWorkspace questionId={resourceId} assessmentId={assessmentId} />
    </div>
  </ProtectedRoute>;
}
