"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Container,
  Group,
  Loader,
  Menu,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { IconAlertCircle, IconDots, IconPlus } from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { QuestionCard, QuestionCardData } from "@/components/QuestionCard";
import { useAuth } from "@/contexts/AuthContext";
import { useERAbility } from "@/hooks/use-er-ability";
import { toERQuestionSubject } from "@/permissions/er-ability";
import { erDiagramService } from "@/services/er-diagram.service";
import { erLabsService } from "@/services/erLabs.service";
import type { ErLabResponse } from "@/types/er-lab.types";

type ERQuestionCardData = QuestionCardData & {
  created_by: number;
  created_by_role: "student" | "staff" | "admin";
};

export default function ERDiagramPage() {
  const router = useRouter();
  const ability = useERAbility();
  const { isStaff } = useAuth();
  const [questions, setQuestions] = useState<ERQuestionCardData[]>([]);
  const [labs, setLabs] = useState<ErLabResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingQuestionId, setDeletingQuestionId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string | null>("student-created");

  const studentCreatedQuestions = useMemo(
    () => questions.filter((question) => question.created_by_role === "student"),
    [questions]
  );
  const staffCreatedQuestions = useMemo(
    () => questions.filter((question) => question.created_by_role === "staff" || question.created_by_role === "admin"),
    [questions]
  );

  const refreshLabs = async () => {
    try {
      const ls = await erLabsService.list();
      setLabs(ls);
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({
        color: "red",
        message: axiosErr.response?.data?.detail || axiosErr.message || "Failed to load ER labs",
      });
    }
  };

  useEffect(() => {
    const fetchAll = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await erDiagramService.getQuestions();
        setQuestions(
          data.map((item) => ({
            id: item.id,
            title: item.title,
            summary: item.problem_statement,
            description: item.problem_statement,
            difficulty: item.difficulty_label,
            created_by: item.created_by,
            created_by_role: item.created_by_role,
          }))
        );
      } catch (err) {
        const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(axiosErr.response?.data?.detail || axiosErr.message || "Failed to load ER questions");
      } finally {
        setLoading(false);
      }
      // Lab fetch is isolated so a lab-API failure doesn't kill the question view.
      refreshLabs();
    };

    fetchAll();
  }, []);

  const handleDeleteQuestion = async (questionId: number) => {
    const shouldDelete = window.confirm(`Delete ER question #${questionId}?`);
    if (!shouldDelete) {
      return;
    }

    try {
      setDeletingQuestionId(questionId);
      setError(null);
      await erDiagramService.deleteQuestion(questionId);
      setQuestions((prev) => prev.filter((item) => item.id !== questionId));
    } catch (err) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      if (axiosErr.response?.status === 403) {
        setError(axiosErr.response?.data?.detail || "Only the question owner or staff can delete this question");
      } else {
        setError(axiosErr.response?.data?.detail || axiosErr.message || "Failed to delete ER question");
      }
    } finally {
      setDeletingQuestionId(null);
    }
  };

  const renderQuestions = (questionList: ERQuestionCardData[], emptyMessage: string) => {
    if (questionList.length === 0) {
      return <Text c="dimmed">{emptyMessage}</Text>;
    }

    return (
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
        {questionList.map((question) => (
          <QuestionCard
            key={question.id}
            data={question}
            showDeleteButton={ability.can("delete", toERQuestionSubject(question))}
            deleteLoading={deletingQuestionId === question.id}
            onDelete={handleDeleteQuestion}
          />
        ))}
      </SimpleGrid>
    );
  };

  const onLabPublishToggle = async (lab: ErLabResponse) => {
    try {
      if (lab.is_published) await erLabsService.unpublish(lab.id);
      else await erLabsService.publish(lab.id);
      refreshLabs();
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: "red", message: axiosErr.response?.data?.detail || axiosErr.message || "Failed" });
    }
  };

  const onLabRunToggle = async (lab: ErLabResponse) => {
    try {
      if (lab.is_running) await erLabsService.stop(lab.id);
      else await erLabsService.start(lab.id);
      refreshLabs();
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: "red", message: axiosErr.response?.data?.detail || axiosErr.message || "Failed" });
    }
  };

  const onLabDelete = async (lab: ErLabResponse) => {
    if (!window.confirm(`Delete "${lab.title}"?`)) return;
    try {
      await erLabsService.remove(lab.id);
      refreshLabs();
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: "red", message: axiosErr.response?.data?.detail || axiosErr.message || "Failed" });
    }
  };

  const renderStaffLabTable = () => {
    if (labs.length === 0) return <Text c="dimmed">No labs yet. Click &quot;New ER Lab&quot; to create one.</Text>;
    return (
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Title</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Updated</Table.Th>
            <Table.Th></Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {labs.map((lab) => (
            <Table.Tr key={lab.id}>
              <Table.Td>
                <a
                  onClick={() => router.push(`/er-diagram/lab/${lab.id}`)}
                  style={{ cursor: "pointer", textDecoration: "underline" }}
                >
                  {lab.title}
                </a>
              </Table.Td>
              <Table.Td>
                <Group gap={4}>
                  <Badge color={lab.is_published ? "green" : "gray"}>
                    {lab.is_published ? "Published" : "Unpublished"}
                  </Badge>
                  <Badge color={lab.is_running ? "blue" : "gray"}>
                    {lab.is_running ? "Running" : "Stopped"}
                  </Badge>
                </Group>
              </Table.Td>
              <Table.Td>{new Date(lab.updated_at).toLocaleString()}</Table.Td>
              <Table.Td>
                <Menu>
                  <Menu.Target>
                    <ActionIcon variant="subtle">
                      <IconDots />
                    </ActionIcon>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item onClick={() => router.push(`/er-diagram/lab/${lab.id}`)}>
                      Manage questions
                    </Menu.Item>
                    <Menu.Item onClick={() => router.push(`/er-diagram/lab/${lab.id}/students`)}>
                      View students
                    </Menu.Item>
                    <Menu.Item onClick={() => onLabPublishToggle(lab)}>
                      {lab.is_published ? "Unpublish" : "Publish"}
                    </Menu.Item>
                    <Menu.Item onClick={() => onLabRunToggle(lab)} disabled={!lab.is_published}>
                      {lab.is_running ? "Stop" : "Start"}
                    </Menu.Item>
                    <Menu.Item color="red" onClick={() => onLabDelete(lab)}>
                      Delete
                    </Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    );
  };

  const renderStudentLabTable = () => {
    if (labs.length === 0) return <Text c="dimmed">No labs available right now.</Text>;
    return (
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Title</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th></Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {labs.map((lab) => (
            <Table.Tr key={lab.id}>
              <Table.Td>{lab.title}</Table.Td>
              <Table.Td>
                <Badge color={lab.is_running ? "blue" : "gray"}>
                  {lab.is_running ? "Running" : "Closed"}
                </Badge>
              </Table.Td>
              <Table.Td>
                {lab.is_running ? (
                  <Button size="xs" onClick={() => router.push(`/er-diagram/lab/${lab.id}/join`)}>
                    Join
                  </Button>
                ) : (
                  <Button
                    size="xs"
                    variant="default"
                    onClick={() => router.push(`/er-diagram/lab/${lab.id}/history`)}
                  >
                    View history
                  </Button>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    );
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>ER Diagram Practice</Title>
            <Text c="dimmed" mt={6}>
              Pick a question and sketch the entities, relationships, and keys.
            </Text>
          </div>
          {activeTab === "lab"
            ? (isStaff && (
                <Button
                  variant="light"
                  rightSection={<IconPlus size={16} />}
                  component="a"
                  href="/er-diagram/lab/new"
                >
                  New ER Lab
                </Button>
              ))
            : (
                <Button
                  variant="light"
                  rightSection={<IconPlus size={16} />}
                  component="a"
                  href="/er-diagram/add"
                >
                  Add Question
                </Button>
              )}
        </Group>

        {loading ? (
          <Group justify="center" py="xl">
            <Loader />
          </Group>
        ) : null}

        {error ? (
          <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
            {error}
          </Alert>
        ) : null}

        {!loading && !error ? (
          <Tabs value={activeTab} onChange={setActiveTab}>
            <Tabs.List>
              <Tabs.Tab value="student-created">Student-created</Tabs.Tab>
              <Tabs.Tab value="staff-created">Staff-created</Tabs.Tab>
              <Tabs.Tab value="lab">Lab</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="student-created" pt="md">
              {renderQuestions(studentCreatedQuestions, "No student-created ER questions saved yet.")}
            </Tabs.Panel>
            <Tabs.Panel value="staff-created" pt="md">
              {renderQuestions(staffCreatedQuestions, "No staff-created ER questions saved yet.")}
            </Tabs.Panel>
            <Tabs.Panel value="lab" pt="md">
              {isStaff ? renderStaffLabTable() : renderStudentLabTable()}
            </Tabs.Panel>
          </Tabs>
        ) : null}
      </Stack>
    </Container>
  );
}
