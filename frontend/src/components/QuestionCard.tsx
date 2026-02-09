import { Badge, Card, Group, Stack, Text, Title } from "@mantine/core";
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

export function QuestionCard({ data }: { data: QuestionCardData }) {
  return (
    <Link href={`/er-diagram/${data.id}`} style={{ textDecoration: "none" }}>
      <Card withBorder radius="md" p="md">
        <Stack gap="xs">
          <Group justify="space-between" align="center">
            <Title order={4}>Q{data.id}</Title>
            <Badge color={difficultyColor[data.difficulty]} variant="light">
              {data.difficulty}
            </Badge>
          </Group>
          <Text c="dimmed" size="sm">
            {data.summary}
          </Text>
        </Stack>
      </Card>
    </Link>
  );
}
