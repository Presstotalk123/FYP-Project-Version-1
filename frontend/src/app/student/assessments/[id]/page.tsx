'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Title,
  Text,
  Stack,
  Button,
  Group,
  Loader,
  Alert,
  Badge,
  Card,
  Divider,
  PasswordInput,
} from '@mantine/core';
import {
  IconAlertCircle,
  IconInfoCircle,
  IconPlayerPlay,
  IconArrowLeft,
  IconClipboardList,
  IconLock,
  IconCircleCheck,
  IconClock,
} from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { StudentAssessmentDetail, AssessmentSessionResponse } from '@/types/assessment.types';
import { studentAssessmentService } from '@/services/studentAssessment.service';

export default function StudentAssessmentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const assessmentId = Number(params.id);

  const [assessment, setAssessment] = useState<StudentAssessmentDetail | null>(null);
  const [session, setSession] = useState<AssessmentSessionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, [assessmentId]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const detail = await studentAssessmentService.getDetail(assessmentId);
      setAssessment(detail);

      if (detail.is_running) {
        try {
          const activeSession = await studentAssessmentService.getSession(assessmentId);
          setSession(activeSession);
        } catch {
          // No active session yet — that's fine
        }
      }
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load assessment');
    } finally {
      setLoading(false);
    }
  };

  const handleJoin = async () => {
    setPasswordError(null);
    try {
      setJoining(true);
      await studentAssessmentService.join(assessmentId, password || undefined);
      router.push(`/student/assessments/${assessmentId}/overview`);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string }; status?: number } };
      const detail = e.response?.data?.detail || 'Failed to join assessment';
      // A 403 is either a wrong password or an already-submitted (single-attempt) block.
      // Only treat it as a password error when the assessment actually has a password.
      if (e.response?.status === 403 && assessment?.has_password) {
        setPasswordError('Incorrect password. Please try again.');
      } else {
        setError(detail);
      }
      setJoining(false);
    }
  };

  const handleContinue = () => {
    router.push(`/student/assessments/${assessmentId}/overview`);
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <Stack gap="md" maw={700}>
          <Group>
            <Button
              variant="subtle"
              leftSection={<IconArrowLeft size={16} />}
              onClick={() => router.push('/student/assessments')}
              size="sm"
            >
              Back to Assessments
            </Button>
          </Group>

          {loading && (
            <Group justify="center" py="xl">
              <Loader size="lg" />
            </Group>
          )}

          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {error}
            </Alert>
          )}

          {!loading && !error && assessment && (
            <Card shadow="sm" padding="xl" radius="md" withBorder>
              <Stack gap="lg">
                <Group justify="space-between" align="flex-start">
                  <Title order={2}>{assessment.title}</Title>
                  <Badge
                    size="lg"
                    color={assessment.is_running ? 'green' : 'yellow'}
                    leftSection={
                      assessment.is_running
                        ? <IconPlayerPlay size={14} />
                        : undefined
                    }
                  >
                    {assessment.is_running ? 'Live' : 'Not Started'}
                  </Badge>
                </Group>

                {assessment.description && (
                  <>
                    <Divider />
                    <Text size="md" style={{ whiteSpace: 'pre-wrap' }}>
                      {assessment.description}
                    </Text>
                  </>
                )}

                {assessment.time_limit_minutes != null && (
                  <Alert icon={<IconClock size={16} />} color="blue" title="Timed assessment">
                    You will have <strong>{assessment.time_limit_minutes} minute
                    {assessment.time_limit_minutes === 1 ? '' : 's'}</strong> once you begin. The
                    countdown starts as soon as you click Join, and the assessment is submitted
                    automatically when time runs out. Time spent waiting for queries to run is
                    credited back to you.
                  </Alert>
                )}

                <Divider />

                {assessment.attempt_complete ? (
                  <Stack gap="md">
                    <Alert icon={<IconCircleCheck size={16} />} color="green" title="Assessment Completed">
                      You have already submitted this assessment. It is a single attempt, so it cannot be retaken.
                    </Alert>
                    {assessment.weighted_score != null && (
                      <Group gap="sm">
                        <Text fw={500}>Your score:</Text>
                        <Badge
                          size="lg"
                          variant="light"
                          color={
                            assessment.weighted_score >= 75
                              ? 'green'
                              : assessment.weighted_score >= 50
                                ? 'yellow'
                                : 'red'
                          }
                        >
                          {assessment.weighted_score}%
                        </Badge>
                      </Group>
                    )}
                  </Stack>
                ) : (
                  <>
                    {!assessment.is_running && (
                      <Alert icon={<IconInfoCircle size={16} />} color="yellow" title="Waiting for staff">
                        This assessment has not been started yet. Please wait for your instructor to begin the session.
                      </Alert>
                    )}

                    {assessment.is_running && session && (
                      <Button
                        size="lg"
                        leftSection={<IconClipboardList size={18} />}
                        onClick={handleContinue}
                      >
                        Continue Assessment
                      </Button>
                    )}

                    {assessment.is_running && !session && (
                      <Stack gap="sm">
                        {assessment.has_password && (
                          <PasswordInput
                            label="Assessment Password"
                            placeholder="Enter the password provided by your instructor"
                            leftSection={<IconLock size={16} />}
                            value={password}
                            onChange={(e) => {
                              setPassword(e.currentTarget.value);
                              setPasswordError(null);
                            }}
                            error={passwordError}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleJoin(); }}
                          />
                        )}
                        <Button
                          size="lg"
                          leftSection={<IconPlayerPlay size={18} />}
                          loading={joining}
                          onClick={handleJoin}
                        >
                          Join Assessment
                        </Button>
                      </Stack>
                    )}
                  </>
                )}
              </Stack>
            </Card>
          )}
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
