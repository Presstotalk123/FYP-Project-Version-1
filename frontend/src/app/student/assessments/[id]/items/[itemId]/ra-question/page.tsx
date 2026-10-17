'use client';

import { useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { AssessmentTimer } from '@/components/assessment/AssessmentTimer';
import { QuestionNavigator } from '@/components/assessment/QuestionNavigator';
import { QuestionWeightBadge } from '@/components/assessment/QuestionWeightBadge';
import { RaQuestionWorkspace } from '@/components/ra/RaQuestionWorkspace';
import { useBlockBrowserBack } from '@/hooks/use-block-browser-back';
import { useWarnBeforeUnload } from '@/hooks/use-warn-before-unload';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { UserRole } from '@/types/user.types';

/** A relational-algebra question inside an assessment (Relational Algebra, FYP). */
export default function AssessmentRaQuestionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const assessmentId = Number(params.id);
  const itemId = Number(params.itemId);
  const resourceId = Number(searchParams.get('resourceId'));
  const weight = Number(searchParams.get('weight')) || undefined;
  const backUrl = `/student/assessments/${assessmentId}/overview`;

  useBlockBrowserBack(true);
  useWarnBeforeUnload(true);

  useEffect(() => {
    if (assessmentId && itemId) {
      studentAssessmentService.visitItem(assessmentId, itemId).catch(() => {
        // Non-critical — ignore errors
      });
    }
  }, [assessmentId, itemId]);

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <div style={{ padding: '12px 16px', display: 'grid', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ marginRight: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
            <AssessmentTimer />
            <QuestionWeightBadge weight={weight} />
          </div>
          <button className="btn btn-brand" style={{ minHeight: 34, padding: '0 12px', fontSize: 13 }}
            onClick={() => router.push(backUrl)}>
            Save and Exit
          </button>
        </div>
        <QuestionNavigator />
        <RaQuestionWorkspace questionId={resourceId} />
      </div>
    </ProtectedRoute>
  );
}
