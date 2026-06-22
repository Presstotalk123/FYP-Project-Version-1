import { ActionIcon, Badge, Card, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { IconTrash } from "@tabler/icons-react";
import Link from "next/link";

type Difficulty = "Easy" | "Medium" | "Hard";

export type QuestionCardData = {
  id: number;
  title: string;
  summary: string;
  description: string;
  difficulty: Difficulty;
};

const difficultyColor: Record<Difficulty, string> = {
  Easy: "green",
  Medium: "yellow",
  Hard: "red",
};

type QuestionCardProps = {
  data: QuestionCardData;
  showDeleteButton?: boolean;
  deleteLoading?: boolean;
  onDelete?: (questionId: number) => Promise<void>;
};

export function QuestionCard({
  data,
  showDeleteButton = false,
  deleteLoading = false,
  onDelete,
}: QuestionCardProps) {
  return (
    <Link href={`/er-diagram/${data.id}`} style={{ textDecoration: "none" }}>
      <Card withBorder radius="md" p="md">
        <Stack gap="xs">
          <Group justify="space-between" align="flex-start">
            <Title order={4}>{data.title}</Title>
            {showDeleteButton && onDelete ? (
              <ActionIcon
                color="red"
                variant="filled"
                aria-label={`Delete question ${data.id}`}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  void onDelete(data.id);
                }}
                disabled={deleteLoading}
              >
                {deleteLoading ? <Loader size={14} color="white" /> : <IconTrash size={16} />}
              </ActionIcon>
            ) : null}
          </Group>
          <Group justify="space-between" align="center">
            <Badge color={difficultyColor[data.difficulty]} variant="light">
              {data.difficulty}
            </Badge>
          </Group>
          <Text c="dimmed" size="sm" lineClamp={4}>
            {data.summary}
          </Text>
        </Stack>
      </Card>
    </Link>
  );
}