'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Drawer,
  ScrollArea,
  Stack,
  Group,
  Text,
  Badge,
  Card,
  SimpleGrid,
  Loader,
  Alert,
} from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { reportService } from '@/services/report.service';
import { queryKeys } from '@/services/query-keys';
import { AssessmentItemComponentScore } from '@/types/assessment.types';

// Shared type/label maps, matching the assessment students page.
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
const scoreColor = (score: number) => (score >= 75 ? 'green' : score >= 50 ? 'yellow' : 'red');

function renderScore(score: number | null | undefined, size: 'sm' | 'lg' = 'sm') {
  if (score == null) return <Text size="sm" c="dimmed">—</Text>;
  return (
    <Badge color={scoreColor(score)} variant="light" size={size}>
      {score}%
    </Badge>
  );
}

// Per-item activity summary, including lab task counts.
function renderItemScore(item: AssessmentItemComponentScore) {
  if (item.item_type === 'sql_question') {
    const correct = item.has_correct_attempt;
    const count = item.attempt_count ?? 0;
    return (
      <Group gap="xs">
        <Badge color={correct ? 'green' : count > 0 ? 'red' : 'gray'} variant="light">
          {correct ? 'Solved' : count > 0 ? 'Not Solved' : 'Not Attempted'}
        </Badge>
        {count > 0 && <Text size="xs" c="dimmed">{count} attempt{count !== 1 ? 's' : ''}</Text>}
      </Group>
    );
  }
  if (item.item_type === 'er_question') {
    return (
      <Badge color={item.visited ? 'blue' : 'gray'} variant="light">
        {item.visited ? 'Visited' : 'Not Visited'}
      </Badge>
    );
  }
  if (item.item_type === 'sql_lab' || item.item_type === 'graph_lab') {
    const correct = item.tasks_correct ?? 0;
    const total = item.tasks_total ?? 0;
    const allDone = total > 0 && correct === total;
    return (
      <Badge color={allDone ? 'green' : correct > 0 ? 'yellow' : 'gray'} variant="light">
        {correct}/{total} tasks
      </Badge>
    );
  }
  return <Text size="sm" c="dimmed">—</Text>;
}

function CountCard({ label, value }: { label: string; value: number }) {
  return (
    <Card withBorder padding="sm" radius="md">
      <Text size="xs" c="dimmed" fw={600} tt="uppercase">{label}</Text>
      <Text size="xl" fw={700}>{value}</Text>
    </Card>
  );
}

interface StudentReportDrawerProps {
  student: { id: number; name: string } | null;
  onClose: () => void;
}

export function StudentReportDrawer({ student, onClose }: StudentReportDrawerProps) {
  const reportQuery = useQuery({
    queryKey: student ? queryKeys.studentFullReport(student.id) : ['studentFullReport', 'none'],
    queryFn: () => reportService.getForStudent(student!.id),
    enabled: student !== null,
  });

  const report = reportQuery.data;

  return (
    <Drawer
      opened={student !== null}
      onClose={onClose}
      title={<Text fw={600}>Report — {student?.name}</Text>}
      position="right"
      size="lg"
      scrollAreaComponent={ScrollArea.Autosize}
    >
      {reportQuery.isLoading && (
        <Group justify="center" py="xl"><Loader /></Group>
      )}

      {reportQuery.error && (
        <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
          {(reportQuery.error as { response?: { data?: { detail?: string } } }).response?.data?.detail
            ?? 'Failed to load the student report.'}
        </Alert>
      )}

      {report && (
        <Stack gap="lg">
          {/* Practice completion */}
          <div>
            <Text fw={600} size="sm" mb="xs">Practice completed</Text>
            <SimpleGrid cols={2} spacing="sm">
              <CountCard label="SQL Questions" value={report.summary.sql_questions_completed} />
              <CountCard label="ER Diagram Questions" value={report.summary.erd_questions_completed} />
              <CountCard label="Graph Labs" value={report.summary.graph_labs_completed} />
              <CountCard label="SQL Labs" value={report.summary.sql_labs_completed} />
            </SimpleGrid>
          </div>

          {/* Assessment scores */}
          <div>
            <Text fw={600} size="sm" mb="xs">Assessment scores</Text>
            {report.assessments.length === 0 ? (
              <Alert icon={<IconAlertCircle size={16} />} color="blue" title="No submitted assessments yet">
                This student hasn&apos;t submitted any assessments.
              </Alert>
            ) : (
              <Stack gap="md">
                {report.assessments.map((a) => (
                  <Card key={a.assessment_id} withBorder padding="md" radius="md">
                    <Stack gap="sm">
                      <Group justify="space-between" align="flex-start" wrap="nowrap">
                        <Stack gap={2} style={{ minWidth: 0 }}>
                          <Text fw={600} size="sm" lineClamp={2}>{a.assessment_title}</Text>
                          {a.submitted_at && (
                            <Text size="xs" c="dimmed">
                              Submitted {new Date(a.submitted_at).toLocaleString()}
                            </Text>
                          )}
                        </Stack>
                        {a.above_average != null && (
                          <Badge color={a.above_average ? 'green' : 'red'} variant="filled">
                            {a.above_average ? 'Above average' : 'Below average'}
                          </Badge>
                        )}
                      </Group>

                      <Group gap="xl">
                        <Stack gap={2}>
                          <Text size="xs" c="dimmed" fw={600} tt="uppercase">Score</Text>
                          {renderScore(a.total_weighted_score, 'lg')}
                        </Stack>
                        <Stack gap={2}>
                          <Text size="xs" c="dimmed" fw={600} tt="uppercase">
                            Cohort avg ({a.student_count})
                          </Text>
                          {renderScore(a.cohort_average, 'lg')}
                        </Stack>
                      </Group>

                      {/* Per-item breakdown, incl. lab task counts */}
                      <Stack gap={6}>
                        {a.items.map((item, idx) => (
                          <Group key={item.assessment_item_id} justify="space-between" wrap="nowrap">
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
                              {renderItemScore(item)}
                              {!!item.weight && (
                                <Text size="xs" c="dimmed">{item.weight}%</Text>
                              )}
                            </Group>
                          </Group>
                        ))}
                      </Stack>
                    </Stack>
                  </Card>
                ))}
              </Stack>
            )}
          </div>
        </Stack>
      )}
    </Drawer>
  );
}
