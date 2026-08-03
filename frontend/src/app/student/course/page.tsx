'use client';

import { useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { CourseChatBubble } from '@/components/course/CourseChatBubble';
import { CourseMarkdown } from '@/components/course/CourseMarkdown';
import { UserRole } from '@/types/user.types';
import { courseService } from '@/services/course.service';
import { queryKeys } from '@/services/query-keys';

export default function StudentCoursePage() {
  // Session-cached (see providers.tsx). Shared `courseInfo` key with the staff
  // editor; a staff save invalidates it so this page refetches the new syllabus.
  const courseQuery = useQuery({
    queryKey: queryKeys.courseInfo,
    queryFn: () => courseService.get(),
  });

  const content = courseQuery.data?.content ?? '';
  const loading = courseQuery.isLoading;
  const error = courseQuery.error
    ? ((courseQuery.error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load course information')
    : null;

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        {/* Header */}
        <div className="page-head">
          <div>
            <h2>Course Information</h2>
            <p>Course syllabus and overview.</p>
          </div>
          <div className="button-row">
            <span className="badge brand-badge">SC2207 / CZ2007</span>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading course information…</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {/* Syllabus */}
        {!loading && !error && (
          <section className="card">
            <CourseMarkdown content={content} />
          </section>
        )}

        {/* Floating course assistant — fed the syllabus Markdown as context */}
        {!loading && !error && content && (
          <CourseChatBubble courseContext={content} />
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
