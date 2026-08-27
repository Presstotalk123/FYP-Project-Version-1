'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Title,
  Button,
  Stack,
  Group,
  Table,
  Badge,
  Loader,
  Alert,
  Text,
  Drawer,
  Card,
  ScrollArea,
  Modal,
  Select,
  Box,
  TextInput,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconAlertCircle,
  IconArrowLeft,
  IconActivity,
  IconEye,
  IconRefresh,
  IconPlus,
  IconSearch,
  IconArrowUp,
  IconArrowDown,
  IconArrowsSort,
} from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { AddErSubmissionModal } from '@/components/admin/AddErSubmissionModal';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import {
  AssessmentStudentRow,
  AssessmentStudentsResponse,
  AssessmentItemComponentScore,
  AssessmentItemAggregateScore,
  StudentComponentScoresResponse,
  AssessmentItemAnalyticsResponse,
} from '@/types/assessment.types';
import { assessmentService } from '@/services/assessment.service';

export default function AssessmentStudentsPage() {
  const params = useParams();
  const router = useRouter();
  const assessmentId = Number(params.id);

  const [data, setData] = useState<AssessmentStudentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Lab-group (class_group) filter
  const [selectedClassGroup, setSelectedClassGroup] = useState<string | null>(null);

  // Name/email search and Score-column sort direction.
  // scoreSort: null = table's default order; 'desc' = highest→lowest; 'asc' = lowest→highest
  const [search, setSearch] = useState('');
  const [scoreSort, setScoreSort] = useState<'asc' | 'desc' | null>(null);

  // Per-question averages, scoped to the current class-group filter (or the whole
  // cohort when unfiltered).
  const [itemAnalytics, setItemAnalytics] = useState<AssessmentItemAnalyticsResponse | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  // Bumped after a submission is added, so the per-question averages refetch. Without
  // it they only reload on an assessment or class-group change, and would sit stale
  // beside a student row that has already moved.
  const [analyticsReloadKey, setAnalyticsReloadKey] = useState(0);

  // Activity drawer
  const [activityStudent, setActivityStudent] = useState<AssessmentStudentRow | null>(null);
  const [scores, setScores] = useState<StudentComponentScoresResponse | null>(null);
  const [scoresLoading, setScoresLoading] = useState(false);
  const [scoresError, setScoresError] = useState<string | null>(null);

  // Reset-attempt confirmation
  const [resetStudent, setResetStudent] = useState<AssessmentStudentRow | null>(null);
  const [resetting, setResetting] = useState(false);

  // "Add submission" target: which student, which ER question, and what the row
  // already knows about their draft. Null closes the dialog.
  const [addTarget, setAddTarget] = useState<{
    studentId: number;
    studentName: string;
    questionId: number;
    questionTitle: string;
    hasSavedDraft: boolean;
    draftUpdatedAt?: string | null;
    hasExistingGrade: boolean;
  } | null>(null);

  // End-and-refresh confirmation (shown only when students are still active).
  const [recomputeOpen, setRecomputeOpen] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  const fetchStudents = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await assessmentService.getAssessmentStudents(assessmentId);
      setData(result);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load students');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStudents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId]);

  useEffect(() => {
    let cancelled = false;
    const fetchItemAnalytics = async () => {
      setAnalyticsLoading(true);
      setAnalyticsError(null);
      try {
        const result = await assessmentService.getAssessmentItemAnalytics(assessmentId, selectedClassGroup);
        if (!cancelled) setItemAnalytics(result);
      } catch (err) {
        if (cancelled) return;
        const e = err as { response?: { data?: { detail?: string } } };
        setAnalyticsError(e.response?.data?.detail || 'Failed to load question averages');
      } finally {
        if (!cancelled) setAnalyticsLoading(false);
      }
    };
    fetchItemAnalytics();
    return () => {
      cancelled = true;
    };
  }, [assessmentId, selectedClassGroup, analyticsReloadKey]);

  const handleResetConfirm = async () => {
    if (!resetStudent) return;
    setResetting(true);
    try {
      await assessmentService.resetStudentAttempt(assessmentId, resetStudent.user_id);
      notifications.show({
        color: 'green',
        title: 'Attempt reset',
        message: `${resetStudent.email} has a clean slate and can retake this assessment.`,
      });
      setResetStudent(null);
      await fetchStudents();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        color: 'red',
        title: 'Reset failed',
        message: e.response?.data?.detail || 'Could not reset the attempt.',
      });
    } finally {
      setResetting(false);
    }
  };

  const handleRecompute = async () => {
    setRecomputing(true);
    try {
      const result = await assessmentService.recomputeScores(assessmentId);
      setRecomputeOpen(false);
      notifications.show({
        color: 'green',
        title: 'Scores refreshed',
        message: `Rescored ${result.updated} student${result.updated === 1 ? '' : 's'} · ${result.submitted} auto-submitted · ${result.er_graded} diagram${result.er_graded === 1 ? '' : 's'} graded.`,
      });
      await fetchStudents();
      setAnalyticsReloadKey((k) => k + 1); // re-pull the per-question averages
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        color: 'red',
        title: 'Refresh failed',
        message: e.response?.data?.detail || 'Could not recompute scores.',
      });
    } finally {
      setRecomputing(false);
    }
  };

  // Shared by the drawer's first load and by the refresh after a submission is added,
  // so both paths read the same endpoint and show the same shape of error.
  const loadScores = async (studentId: number) => {
    setScoresError(null);
    setScoresLoading(true);
    try {
      const result = await assessmentService.getStudentComponentScores(assessmentId, studentId);
      setScores(result);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setScoresError(e.response?.data?.detail || 'Failed to load scores');
    } finally {
      setScoresLoading(false);
    }
  };

  const openActivityDrawer = async (student: AssessmentStudentRow) => {
    setActivityStudent(student);
    setScores(null);
    await loadScores(student.user_id);
  };

  const closeActivityDrawer = () => {
    setActivityStudent(null);
    setScores(null);
    setScoresError(null);
  };

  const itemTypeBadgeColor: Record<string, string> = {
    sql_question: 'blue',
    er_question: 'violet',
    sql_lab: 'orange',
    graph_lab: 'teal',
  };

  const itemTypeLabel: Record<string, string> = {
    sql_question: 'SQL Question',
    er_question: 'ER Question',
    sql_lab: 'SQL Lab',
    graph_lab: 'Graph Lab',
  };

  // Colour a weighted score (0-100) green/yellow/red like a gradebook.
  const scoreColor = (score: number) =>
    score >= 75 ? 'green' : score >= 50 ? 'yellow' : 'red';

  const renderWeightedScore = (score: number | null | undefined, size: 'sm' | 'lg' = 'sm') =>
    score == null ? (
      <Text size="sm" c="dimmed">—</Text>
    ) : (
      <Badge color={scoreColor(score)} variant="light" size={size}>
        {score}%
      </Badge>
    );

  // "4 of 12 correct · 18 attempts by 9 students (avg 2.0)" — the headcounts behind the
  // averages above. The attempts half is dropped when nothing was recorded, so an ER item
  // graded by the Dify engine (which writes no er_submissions rows) reads as correct-only
  // instead of claiming zero attempts.
  const renderItemCounts = (item: AssessmentItemAggregateScore, rosterSize: number) => {
    const correct = item.correct_count ?? 0;
    const attempted = item.attempted_count ?? 0;
    const attempts = item.total_attempts ?? 0;
    const parts = [`${correct} of ${rosterSize} correct`];
    if (attempts > 0) {
      parts.push(
        `${attempts} attempt${attempts === 1 ? '' : 's'} by ${attempted} student${attempted === 1 ? '' : 's'}` +
        (item.avg_attempts != null ? ` (avg ${item.avg_attempts})` : '')
      );
    }
    return <Text size="xs" c="dimmed">{parts.join(' · ')}</Text>;
  };

  const renderItemScore = (item: AssessmentItemComponentScore, studentId: number) => {
    if (item.item_type === 'sql_question') {
      const correct = item.has_correct_attempt;
      const count = item.attempt_count ?? 0;
      return (
        <Group gap="xs">
          <Badge color={correct ? 'green' : count > 0 ? 'red' : 'gray'} variant="light">
            {correct ? 'Solved' : count > 0 ? 'Not Solved' : 'Not Attempted'}
          </Badge>
          {count > 0 && (
            <Text size="sm" c="dimmed">{count} attempt{count !== 1 ? 's' : ''}</Text>
          )}
          <Button
            size="xs"
            variant="light"
            color="teal"
            leftSection={<IconEye size={12} />}
            /* item_id is the assessment's own clone of the question, which is what
               the student actually attempted, so this lands on their real work. */
            onClick={() => router.push(`/admin/sql-analytics/${item.item_id}?student=${studentId}`)}
          >
            View Submissions
          </Button>
        </Group>
      );
    }

    if (item.item_type === 'er_question') {
      // The assessment timer closes the session without submitting the open diagram,
      // so a saved draft with no grade is the normal shape of a lost attempt — and a
      // different situation from a student who never drew anything.
      const graded = item.has_er_grade === true;
      const draftOnly = !graded && item.has_saved_draft === true;
      const erPercent = Math.round((item.score_fraction ?? 0) * 100);
      return (
        <Group gap="xs">
          {graded ? (
            // Coloured like every other score on this page, so a graded 0% cannot
            // read as a pass just because it was graded.
            <Badge color={scoreColor(erPercent)} variant="light">
              Graded {erPercent}%
            </Badge>
          ) : draftOnly ? (
            <Badge color="orange" variant="light">Draft saved, not submitted</Badge>
          ) : (
            <Badge color="gray" variant="light">
              {item.visited ? 'Not attempted' : 'Not visited'}
            </Badge>
          )}
          {/* Neutral in every state, on purpose. This row spends its colour on
              meaning — green/yellow/red for the score, orange for a waiting draft,
              teal for the page's ordinary actions — so a grey button competes with
              none of it. The badge beside it is what says whether to act. */}
          <Button
            size="xs"
            variant="light"
            color="gray.7"
            leftSection={<IconPlus size={12} />}
            onClick={() =>
              setAddTarget({
                studentId,
                studentName:
                  activityStudent?.name || activityStudent?.email || `student ${studentId}`,
                questionId: item.item_id,
                questionTitle: item.item_title,
                hasSavedDraft: item.has_saved_draft === true,
                draftUpdatedAt: item.draft_updated_at,
                hasExistingGrade: graded,
              })
            }
          >
            Add Submission
          </Button>
          <Button
            size="xs"
            variant="light"
            color="teal"
            leftSection={<IconEye size={12} />}
            onClick={() => router.push(`/admin/er-analytics/${item.item_id}?student=${studentId}`)}
          >
            View Submissions
          </Button>
        </Group>
      );
    }

    if (item.item_type === 'sql_lab' || item.item_type === 'graph_lab') {
      const correct = item.tasks_correct ?? 0;
      const total = item.tasks_total ?? 0;
      const allDone = total > 0 && correct === total;
      return (
        <Group gap="xs">
          <Badge color={allDone ? 'green' : correct > 0 ? 'yellow' : 'gray'} variant="light">
            {correct}/{total} tasks
          </Badge>
          <Button
            size="xs"
            variant="light"
            color="teal"
            leftSection={<IconEye size={12} />}
            onClick={() => router.push(`/admin/labs/${item.item_id}/review/${studentId}`)}
          >
            View Lab Activity
          </Button>
        </Group>
      );
    }

    return <Text size="sm" c="dimmed">—</Text>;
  };

  // Distinct lab groups present in the student list, and the filtered rows.
  const classGroups = data
    ? Array.from(
        new Set(data.students.map((s) => s.class_group).filter((c): c is string => !!c))
      ).sort()
    : [];
  const q = search.trim().toLowerCase();
  const filteredStudents = data
    ? data.students.filter(
        (s) =>
          (!selectedClassGroup || s.class_group === selectedClassGroup) &&
          (!q ||
            s.email.toLowerCase().includes(q) ||
            (s.name ?? '').toLowerCase().includes(q))
      )
    : [];
  // Sorted view for rendering. Nulls (no score) always sort last, regardless of
  // direction, so an empty score never masquerades as the lowest or highest.
  const sortedStudents =
    scoreSort === null
      ? filteredStudents
      : [...filteredStudents].sort((a, b) => {
          const sa = a.weighted_score;
          const sb = b.weighted_score;
          if (sa == null && sb == null) return 0;
          if (sa == null) return 1;
          if (sb == null) return -1;
          return scoreSort === 'desc' ? sb - sa : sa - sb;
        });
  // Students still mid-attempt — ending & refreshing will force-submit them, so warn first.
  const activeCount = data ? data.students.filter((s) => s.is_active).length : 0;

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Stack gap="md">
          <Group justify="space-between">
            <Button
              variant="subtle"
              leftSection={<IconArrowLeft size={16} />}
              onClick={() => router.push('/admin/assessments')}
            >
              Back
            </Button>
            <Button
              leftSection={<IconRefresh size={16} />}
              loading={recomputing}
              onClick={() => (activeCount > 0 ? setRecomputeOpen(true) : handleRecompute())}
            >
              End and refresh
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

          {data && (
            <>
              <Title order={2}>
                &ldquo;{data.assessment_title}&rdquo; — Student Activity
              </Title>

              {data.students.length === 0 ? (
                <Alert icon={<IconAlertCircle size={16} />} color="blue" title="No Students">
                  No students have joined this assessment yet.
                </Alert>
              ) : (
                <>
                  <Group>
                    <TextInput
                      leftSection={<IconSearch size={14} />}
                      placeholder="Search name or email…"
                      value={search}
                      onChange={(e) => setSearch(e.currentTarget.value)}
                      style={{ width: 250 }}
                    />
                    <Select
                      placeholder="Filter by Class Group"
                      data={classGroups}
                      value={selectedClassGroup}
                      onChange={setSelectedClassGroup}
                      clearable
                      searchable
                      style={{ width: 250 }}
                    />
                  </Group>

                  <Card withBorder padding="md" radius="md">
                    <Stack gap="sm">
                      <Group justify="space-between" align="center">
                        <Stack gap={2}>
                          <Text size="sm" fw={600}>
                            Average Score — {selectedClassGroup ? selectedClassGroup : 'All Students'}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {itemAnalytics ? `${itemAnalytics.student_count} student${itemAnalytics.student_count !== 1 ? 's' : ''}` : '—'}
                          </Text>
                        </Stack>
                        {analyticsLoading ? (
                          <Loader size="sm" />
                        ) : (
                          renderWeightedScore(itemAnalytics?.avg_weighted_score, 'lg')
                        )}
                      </Group>

                      {analyticsError && (
                        <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
                          {analyticsError}
                        </Alert>
                      )}

                      {!analyticsLoading && !analyticsError && itemAnalytics && (
                        <Stack gap={10}>
                          {itemAnalytics.items.map((item, idx) => (
                            <Stack key={item.assessment_item_id} gap={4}>
                              <Group justify="space-between" wrap="nowrap">
                                <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                                  <Text size="xs" c="dimmed" fw={500}>#{idx + 1}</Text>
                                  <Badge
                                    size="xs"
                                    color={itemTypeBadgeColor[item.item_type] ?? 'gray'}
                                    variant="filled"
                                  >
                                    {itemTypeLabel[item.item_type] ?? item.item_type}
                                  </Badge>
                                  <Text size="sm" lineClamp={1}>{item.item_title}</Text>
                                </Group>
                                <Group gap="sm" wrap="nowrap">
                                  {(item.item_type === 'sql_lab' || item.item_type === 'graph_lab') && (
                                    <Text size="xs" c="dimmed">
                                      {item.avg_tasks_correct != null && item.tasks_total != null
                                        ? `${item.avg_tasks_correct} / ${item.tasks_total} tasks avg`
                                        : '—'}
                                    </Text>
                                  )}
                                  {renderWeightedScore(
                                    item.avg_score_fraction != null ? Math.round(item.avg_score_fraction * 1000) / 10 : null
                                  )}
                                </Group>
                              </Group>
                              <Box pl="lg">
                                {renderItemCounts(item, itemAnalytics.student_count)}
                              </Box>
                              {(item.item_type === 'sql_lab' || item.item_type === 'graph_lab') && !!item.tasks?.length && (
                                <Stack gap={2} pl="lg">
                                  {item.tasks.map((task) => (
                                    <Group key={task.task_id} justify="space-between" wrap="nowrap">
                                      <Text size="xs" c="dimmed" lineClamp={1}>{task.task_title}</Text>
                                      <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
                                        {task.correct_count ?? 0}/{itemAnalytics.student_count} correct
                                        {(task.total_attempts ?? 0) > 0 && ` · ${task.total_attempts} attempts`}
                                        {task.success_rate != null ? ` · ${task.success_rate}%` : ''}
                                      </Text>
                                    </Group>
                                  ))}
                                </Stack>
                              )}
                            </Stack>
                          ))}
                        </Stack>
                      )}
                    </Stack>
                  </Card>

                  {filteredStudents.length === 0 ? (
                    <Alert icon={<IconAlertCircle size={16} />} color="blue" title="No Students">
                      No students in this class group.
                    </Alert>
                  ) : (
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Email</Table.Th>
                      <Table.Th>Name</Table.Th>
                      <Table.Th>Class</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th
                        style={{ cursor: 'pointer', userSelect: 'none' }}
                        onClick={() =>
                          setScoreSort((s) =>
                            s === 'desc' ? 'asc' : s === 'asc' ? null : 'desc'
                          )
                        }
                      >
                        <Group gap={4} wrap="nowrap">
                          Score
                          {scoreSort === 'desc' ? (
                            <IconArrowDown size={14} />
                          ) : scoreSort === 'asc' ? (
                            <IconArrowUp size={14} />
                          ) : (
                            <IconArrowsSort size={14} style={{ opacity: 0.5 }} />
                          )}
                        </Group>
                      </Table.Th>
                      <Table.Th>Joined At</Table.Th>
                      <Table.Th>Submitted At</Table.Th>
                      <Table.Th>Actions</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {sortedStudents.map((student) => (
                      <Table.Tr key={student.user_id}>
                        <Table.Td>
                          <Text size="sm" fw={500}>{student.email}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{student.name || '—'}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{student.class_group ?? '—'}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge color={student.is_active ? 'blue' : 'green'} variant="light">
                            {student.is_active ? 'Active' : 'Submitted'}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          {renderWeightedScore(student.weighted_score)}
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{new Date(student.joined_at).toLocaleString()}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            {student.submitted_at
                              ? new Date(student.submitted_at).toLocaleString()
                              : '—'}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs">
                            <Button
                              size="xs"
                              variant="light"
                              color="teal"
                              leftSection={<IconActivity size={14} />}
                              onClick={() => openActivityDrawer(student)}
                            >
                              View Activity
                            </Button>
                            <Button
                              size="xs"
                              variant="light"
                              color="red"
                              leftSection={<IconRefresh size={14} />}
                              onClick={() => setResetStudent(student)}
                            >
                              Reset
                            </Button>
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
                  )}
                </>
              )}
            </>
          )}
        </Stack>

        {/* Reset-attempt confirmation */}
        <Modal
          opened={!!resetStudent}
          onClose={() => (resetting ? null : setResetStudent(null))}
          title={<Text fw={600}>Reset attempt?</Text>}
          centered
        >
          <Stack gap="md">
            <Text size="sm">
              This permanently erases <b>{resetStudent?.email}</b>&rsquo;s work on this assessment
              (all submissions, query history, and progress) and removes their session, giving them a
              clean slate to retake it. Their standalone practice is not affected. This cannot be undone.
            </Text>
            <Group justify="flex-end" gap="sm">
              <Button variant="default" onClick={() => setResetStudent(null)} disabled={resetting}>
                Cancel
              </Button>
              <Button color="red" loading={resetting} onClick={handleResetConfirm}>
                Reset attempt
              </Button>
            </Group>
          </Stack>
        </Modal>

        {/* End-and-refresh confirmation (only shown when students are still active) */}
        <Modal
          opened={recomputeOpen}
          onClose={() => (recomputing ? null : setRecomputeOpen(false))}
          title={<Text fw={600}>End and refresh?</Text>}
          centered
        >
          <Stack gap="md">
            <Text size="sm">
              <b>{activeCount}</b> student{activeCount === 1 ? ' is' : 's are'} still in progress.
              Ending now <b>force-submits {activeCount === 1 ? 'them' : 'them all'}</b> (including
              anyone past their time limit), grades everyone&rsquo;s latest saved ER diagram, and
              recomputes weighted scores. The assessment itself stays open. Grading diagrams can
              take a minute or two.
            </Text>
            <Group justify="flex-end" gap="sm">
              <Button variant="default" onClick={() => setRecomputeOpen(false)} disabled={recomputing}>
                Cancel
              </Button>
              <Button color="red" loading={recomputing} onClick={handleRecompute}>
                End and refresh
              </Button>
            </Group>
          </Stack>
        </Modal>

        {/* Component-wise activity drawer */}
        <Drawer
          opened={!!activityStudent}
          onClose={closeActivityDrawer}
          title={
            <Text fw={600}>
              Activity — {activityStudent?.email}
            </Text>
          }
          position="right"
          size="lg"
          scrollAreaComponent={ScrollArea.Autosize}
        >
          {scoresLoading && (
            <Group justify="center" py="xl">
              <Loader />
            </Group>
          )}

          {scoresError && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {scoresError}
            </Alert>
          )}

          {scores && (
            <Stack gap="sm">
              <Card withBorder padding="md" radius="md" bg="var(--mantine-color-default-hover)">
                <Group justify="space-between" align="center">
                  <Stack gap={2}>
                    <Text size="sm" fw={600}>Weighted Score</Text>
                    <Text size="xs" c="dimmed">
                      Based on each question&rsquo;s weightage and this student&rsquo;s activity.
                    </Text>
                  </Stack>
                  {scores.total_weighted_score == null ? (
                    <Text size="sm" c="dimmed">Not weighted</Text>
                  ) : (
                    <Text size="xl" fw={700} c={scoreColor(scores.total_weighted_score)}>
                      {scores.total_weighted_score}
                      <Text span size="sm" c="dimmed"> / 100</Text>
                    </Text>
                  )}
                </Group>
              </Card>

              {scores.items.map((item, idx) => (
                <Card key={item.assessment_item_id} withBorder padding="sm" radius="md">
                  <Group justify="space-between" align="flex-start" wrap="nowrap">
                    <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
                      <Group gap="xs">
                        <Text size="xs" c="dimmed" fw={500}>#{idx + 1}</Text>
                        <Badge
                          size="xs"
                          color={itemTypeBadgeColor[item.item_type] ?? 'gray'}
                          variant="filled"
                        >
                          {itemTypeLabel[item.item_type] ?? item.item_type}
                        </Badge>
                        {!!item.weight && (
                          <Badge size="xs" color="indigo" variant="light">
                            {item.weight}% weight
                          </Badge>
                        )}
                      </Group>
                      <Text size="sm" fw={500} lineClamp={2}>{item.item_title}</Text>
                    </Stack>
                    <Stack gap={4} align="flex-end">
                      {renderItemScore(item, activityStudent!.user_id)}
                      {item.weighted_points != null && !!item.weight && (
                        <Text size="xs" c="dimmed">
                          {item.weighted_points} / {item.weight} pts
                        </Text>
                      )}
                    </Stack>
                  </Group>
                </Card>
              ))}
            </Stack>
          )}
        </Drawer>

        {addTarget && (
          <AddErSubmissionModal
            opened
            onClose={() => setAddTarget(null)}
            onGraded={() => {
              // A new grade moves three things: this student's item score and total in
              // the drawer, their row in the table, and the per-question averages at the
              // top. All three are re-read rather than patched, so none can go stale.
              void loadScores(addTarget.studentId);
              void fetchStudents();
              setAnalyticsReloadKey((k) => k + 1);
            }}
            {...addTarget}
          />
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
