"use client";

import { Badge, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { getRubricStatusMeta, type RubricDisplayGroup } from "@/utils/er-rubric-results";

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
