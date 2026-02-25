import { Badge, Card, Group, Stack, Text, Title, Button } from "@mantine/core";
import Link from "next/link";

type Difficulty = "Easy" | "Medium" | "Hard";

export type QuestionCardData = {
  id: number;
  title: string;
  summary: string;
  description: string;
  difficulty: Difficulty;
};

type QuestionCardProps = {
  data: QuestionCardData;
  showDeleteButton: boolean;
  deleteLoading: boolean;
  onDelete: (questionId: number) => Promise<void>;
};

const difficultyColor: Record<Difficulty, string> = {
  Easy: "green",
  Medium: "yellow",
  Hard: "red",
};

export function QuestionCard({
  data,
  showDeleteButton,
  deleteLoading,
  onDelete,
}: QuestionCardProps) {
  return (
    <Link href={`/er-diagram/${data.id}`} style={{ textDecoration: "none" }}>
      <Card withBorder radius="md" p="md">
        <Stack gap="xs">
          <Group justify="space-between" align="center">
            <Title order={4}>{data.title}</Title>
            <Badge color={difficultyColor[data.difficulty]} variant="light">
              {data.difficulty}
            </Badge>
          </Group>

          <Text c="dimmed" size="sm" lineClamp={4}>
            {data.summary}
          </Text>

          {showDeleteButton && (
            <Button
              color="red"
              loading={deleteLoading}
              onClick={(e) => {
                e.preventDefault(); // VERY IMPORTANT
                onDelete(data.id);
              }}
            >
              Delete
            </Button>
          )}
        </Stack>
      </Card>
    </Link>
  );
}