"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Stack, Title, Group, Table, Badge, Button, Text } from "@mantine/core";
import { erLabsService } from "@/services/erLabs.service";
import type { ErLabQuestionResponse, ErLabMyScoresResponse } from "@/types/er-lab.types";

export default function StudentErLabWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const labId = Number(params.id);
  const [questions, setQuestions] = useState<ErLabQuestionResponse[]>([]);
  const [scores, setScores] = useState<ErLabMyScoresResponse | null>(null);

  useEffect(() => {
    erLabsService.getSession(labId).catch(() => router.push(`/er-diagram/lab/${labId}/join`));
    Promise.all([erLabsService.listQuestions(labId), erLabsService.myScores(labId)])
      .then(([qs, sc]) => {
        setQuestions(qs);
        setScores(sc);
      })
      .catch(() => {
        // Non-fatal: table renders empty; the join-redirect above handles missing sessions.
      });
  }, [labId, router]);

  const bestByQ = useMemo(() => {
    const m = new Map<number, number | null>();
    scores?.questions.forEach((q) => m.set(q.er_lab_question_id, q.best_percent));
    return m;
  }, [scores]);

  const onExit = async () => {
    try {
      await erLabsService.exitSession(labId);
    } catch {
      // best effort
    }
    router.push("/er-diagram");
  };

  return (
    <Stack p="md">
      <Group justify="space-between">
        <Title order={2}>Lab questions</Title>
        <Button variant="default" onClick={onExit}>
          Exit lab
        </Button>
      </Group>
      <Text c="dimmed">Pick a question to attempt. Your best score per question is shown.</Text>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>#</Table.Th>
            <Table.Th>Title</Table.Th>
            <Table.Th>Difficulty</Table.Th>
            <Table.Th>Best score</Table.Th>
            <Table.Th></Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {questions.map((q) => {
            const best = bestByQ.get(q.id);
            return (
              <Table.Tr
                key={q.id}
                style={{ cursor: "pointer" }}
                onClick={() => router.push(`/er-diagram/lab/${labId}/question/${q.id}`)}
              >
                <Table.Td>{q.order_index}</Table.Td>
                <Table.Td>{q.title}</Table.Td>
                <Table.Td>
                  <Badge size="sm">{q.difficulty_label}</Badge>
                </Table.Td>
                <Table.Td>{best != null ? `${best.toFixed(0)}%` : "—"}</Table.Td>
                <Table.Td>
                  <Button size="xs">Attempt</Button>
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
