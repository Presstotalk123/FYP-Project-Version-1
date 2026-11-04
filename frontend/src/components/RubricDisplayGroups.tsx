"use client";

import { Badge, Group, Paper, Stack, Text, Title } from "@mantine/core";
import {
  formatScoreValue,
  getRubricStatusMeta,
  type RubricDeductionItem,
  type RubricDisplayGroup,
} from "@/utils/er-rubric-results";

/**
 * What the score's deduction for extra elements is made of: one card per extra
 * that cost points, with the grader's reason, styled like the criteria cards.
 * Renders nothing when nothing was deducted.
 */
export function RubricDeductions({ items }: { items: RubricDeductionItem[] }) {
  if (items.length === 0) return null;
  const total = items.reduce((sum, item) => sum + item.points, 0);
  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center" gap="sm">
        <Title order={5}>Deductions</Title>
        <Badge variant="outline" color="red" radius="xl">
          −{formatScoreValue(total)} points
        </Badge>
      </Group>
      <Text size="sm" c="dimmed">
        Points taken off for drawn elements the rubric does not ask for.
      </Text>
      {items.map((item) => (
        <Paper withBorder radius="md" p="md" key={item.key}>
          <Stack gap="xs">
            <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap">
              <Text fw={600} size="sm" style={{ flex: 1 }}>
                {item.title}
              </Text>
              <Badge color="red" radius="xl" variant="light">
                −{formatScoreValue(item.points)} points
              </Badge>
            </Group>
            {item.reason ? (
              <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>
                {item.reason}
              </Text>
            ) : null}
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}

/**
 * The rubric checklist as students read it after a submission: dimension groups
 * of criteria cards, each with its status badge and grader feedback. Shared by
 * the student workspace's Rubric tab and the staff editor's preview, so what
 * staff preview is the student rendering itself, not a copy that can drift.
 */
export function RubricDisplayGroups({ groups }: { groups: RubricDisplayGroup[] }) {
  return (
    <>
      {groups.map((group) => (
        <Stack gap="sm" key={group.key}>
          <Group justify="space-between" align="center" gap="sm">
            <Title order={5}>{group.label}</Title>
            <Badge variant="outline" color="gray" radius="xl">
              {group.items.length} item{group.items.length === 1 ? "" : "s"}
            </Badge>
          </Group>

          {group.items.map((item) => {
            const statusMeta = getRubricStatusMeta(item.status);
            return (
              <Paper withBorder radius="md" p="md" key={item.id}>
                <Stack gap="xs">
                  <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap">
                    <Text fw={600} size="sm" style={{ flex: 1 }}>
                      {item.requirementText}
                    </Text>
                    <Badge
                      color={statusMeta.color}
                      radius="xl"
                      variant={item.status === "not_evaluated" ? "outline" : "light"}
                    >
                      {statusMeta.label}
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>
                    {item.feedbackText}
                  </Text>
                  <Group gap="xs" wrap="wrap">
                    <Badge variant="outline" color="gray" radius="xl">
                      ID {item.id}
                    </Badge>
                    <Badge variant="outline" radius="xl">
                      {item.requirementLevelLabel}
                    </Badge>
                    <Badge variant="outline" color="gray" radius="xl">
                      {item.pointsLabel}
                    </Badge>
                  </Group>
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      ))}
    </>
  );
}
