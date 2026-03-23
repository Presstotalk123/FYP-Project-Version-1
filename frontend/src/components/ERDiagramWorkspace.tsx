"use client";

import { useEffect, useRef, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Container,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { Dropzone, IMAGE_MIME_TYPE } from "@mantine/dropzone";
import Link from "next/link";
import { IconAlertCircle, IconArrowLeft, IconPhoto, IconUpload, IconX } from "@tabler/icons-react";
import { ChatPanel } from "@/components/ChatPanel";
import { DrawioBoard } from "@/components/DrawioBoard";
import { erDiagramService } from "@/services/er-diagram.service";
import type {
  ERSubmissionRequest,
  ERSubmissionResponse,
  ERSubmissionStructuredOutput,
  ERSubmissionStreamEvent,
} from "@/types/er-diagram.types";

export type ERDiagramWorkspaceQuestion = {
  id: number;
  title: string;
  description: string;
  difficulty: "Easy" | "Medium" | "Hard";
  rubric_md: string;
  show_rubric_on_attempt: boolean;
};

type WorkspaceProps = {
  question: ERDiagramWorkspaceQuestion;
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isObjectArray = (value: unknown): value is Record<string, unknown>[] =>
  Array.isArray(value) && value.every((item) => isObject(item));

const isSubmissionPayload = (value: unknown): value is ERSubmissionStructuredOutput => {
  if (!isObject(value)) return false;
  return (
    isObject(value.score) &&
    isObjectArray(value.checks) &&
    typeof value.student_message === "string" &&
    value.student_message.trim().length > 0
  );
};

const parseSubmissionPayload = (
  structuredOutput: unknown,
  text: string | null | undefined,
): ERSubmissionStructuredOutput | null => {
  if (structuredOutput && isSubmissionPayload(structuredOutput)) {
    return structuredOutput;
  }
  const raw = text?.trim();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (isSubmissionPayload(parsed)) {
      return parsed;
    }
  } catch {
    // Non-JSON submission text is expected in some workflows.
  }
  return null;
};

const getSubmissionPercent = (structuredOutput: ERSubmissionStructuredOutput | null): number | null => {
  if (!structuredOutput || !isObject(structuredOutput.score)) {
    return null;
  }
  const rawPercent = structuredOutput.score.percent;
  if (typeof rawPercent === "number" && Number.isFinite(rawPercent)) {
    return rawPercent;
  }
  if (typeof rawPercent === "string") {
    const parsed = Number(rawPercent);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
};

export function ERDiagramWorkspace({ question }: WorkspaceProps) {
  const [submissionMode, setSubmissionMode] = useState<"drawio" | "image" | null>(null);
  const [submissionImageFiles, setSubmissionImageFiles] = useState<File[]>([]);
  const [chatSending, setChatSending] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [latestStudentMessage, setLatestStudentMessage] = useState<string | null>(null);
  const [latestScorePercent, setLatestScorePercent] = useState<number | null>(null);
  const [hasSubmittedAttempt, setHasSubmittedAttempt] = useState(false);
  const [rightPanelTab, setRightPanelTab] = useState<"ai-chat" | "rubric">("ai-chat");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [leftPercent, setLeftPercent] = useState(70);
  const [isDragging, setIsDragging] = useState(false);
  const showRubricTab = question.show_rubric_on_attempt && hasSubmittedAttempt;

  useEffect(() => {
    if (!showRubricTab && rightPanelTab === "rubric") {
      setRightPanelTab("ai-chat");
    }
  }, [showRubricTab, rightPanelTab]);

  const updateWidthFromPointer = (clientX: number) => {
    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = clientX - rect.left;
    const nextPercent = (x / rect.width) * 100;
    const clamped = Math.min(75, Math.max(30, nextPercent));
    setLeftPercent(clamped);
  };

  const getErrorMessage = (err: unknown): string => {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
    return axiosErr.response?.data?.detail || axiosErr.message || "Request failed";
  };

  const handleQuery = async (message: string): Promise<string> => {
    const response = await erDiagramService.submit({
      question_id: question.id,
      mode: "Query",
      student_query: message,
    });
    return response.text;
  };

  const runSubmitStream = async (payload: ERSubmissionRequest): Promise<void> => {
    setSubmitLoading(true);
    setSubmitError(null);
    setLatestScorePercent(null);

    try {
      let finalResult: ERSubmissionResponse | null = null;
      for await (const event of erDiagramService.submitStream(payload)) {
        const typedEvent = event as ERSubmissionStreamEvent;
        if (typedEvent.event === "token") {
          continue;
        }
        if (typedEvent.event === "structured_output") {
          continue;
        }
        if (typedEvent.event === "done") {
          const parsedStructuredOutput = parseSubmissionPayload(typedEvent.data.structured_output, typedEvent.data.text);

          const normalizedResult: ERSubmissionResponse = {
            ...typedEvent.data,
            text: typedEvent.data.text || "",
            structured_output: parsedStructuredOutput || typedEvent.data.structured_output || null,
          };

          finalResult = normalizedResult;
          const parsedPercent = getSubmissionPercent(parsedStructuredOutput);
          if (parsedPercent !== null) {
            setLatestScorePercent(parsedPercent);
          }

          const studentMessage = parsedStructuredOutput?.student_message?.trim();
          if (studentMessage) {
            setLatestStudentMessage(studentMessage);
          } else if (normalizedResult.text.trim()) {
            setLatestStudentMessage(normalizedResult.text.trim());
          }
          continue;
        }
        if (typedEvent.event === "error") {
          throw new Error(typedEvent.data.detail || "Submission stream failed");
        }
      }

      if (!finalResult) {
        throw new Error("Submission stream interrupted before completion.");
      }
      setHasSubmittedAttempt(true);
    } catch (err) {
      setSubmitError(getErrorMessage(err));
    } finally {
      setSubmitLoading(false);
    }
  };

  const handleSubmitDrawioImage = async (imageFile: File) => {
    if (chatSending) return;
    if (!imageFile || imageFile.size === 0) {
      setSubmitError("Draw.io PNG export is empty. Please export again and retry.");
      return;
    }

    setSubmitError(null);

    await runSubmitStream({
        question_id: question.id,
        mode: "Submit",
        erd_img: imageFile,
      });
  };

  const handleSubmitImage = async () => {
    if (chatSending) return;
    const image = submissionImageFiles[0];
    if (!image) {
      setSubmitError("Please select an image before submitting.");
      return;
    }

    await runSubmitStream({
        question_id: question.id,
        mode: "Submit",
        erd_img: image,
      });
  };

  return (
    <Container fluid px="sm" py="md">
      <Stack gap="md">
        <Group align="baseline" gap="sm">
          <ActionIcon
            component={Link}
            href="/er-diagram"
            variant="subtle"
            size="sm"
            aria-label="Back to ER diagram list"
          >
            <IconArrowLeft size={18} />
          </ActionIcon>
          <Title order={2}>{question.title}</Title>
          <Text c="dimmed" mt={4}>
            Difficulty: {question.difficulty}
          </Text>
        </Group>
        <Box
          ref={containerRef}
          style={{
            display: "flex",
            gap: 0,
            alignItems: "stretch",
            border: "1px solid var(--mantine-color-gray-3)",
            borderRadius: 12,
            overflow: "hidden",
            width: "100%",
          }}
        >
          <Box
            style={{
              flex: `0 0 ${leftPercent}%`,
              minWidth: 320,
              background: "var(--mantine-color-body)",
              padding: 16,
            }}
          >
            <Stack gap="sm">
              <Group align="center" justify="space-between">
                <Title order={4}>Problem</Title>
                {latestScorePercent !== null ? (
                  <Badge color="green" variant="light" size="lg">
                    Score: {latestScorePercent}%
                  </Badge>
                ) : null}
              </Group>
              <Text>{question.description}</Text>

              <Stack gap="sm">
                <Group justify="space-between" align="center">
                  <Title order={5}>Submission Method</Title>
                  {submissionMode ? (
                    <Button variant="subtle" size="xs" onClick={() => setSubmissionMode(null)}>
                      Change
                    </Button>
                  ) : null}
                </Group>

                {!submissionMode ? (
                  <Stack gap="sm">
                    <Paper
                      withBorder
                      radius="md"
                      p="md"
                      style={{ cursor: "pointer" }}
                      onClick={() => setSubmissionMode("drawio")}
                    >
                      <Stack gap={4}>
                        <Text fw={600}>Submit via draw.io</Text>
                        <Text size="sm" c="dimmed">
                          Open the draw.io editor and submit the exported PNG image.
                        </Text>
                      </Stack>
                    </Paper>
                    <Paper
                      withBorder
                      radius="md"
                      p="md"
                      style={{ cursor: "pointer" }}
                      onClick={() => setSubmissionMode("image")}
                    >
                      <Stack gap={4}>
                        <Text fw={600}>Submit via image file</Text>
                        <Text size="sm" c="dimmed">
                          Upload a PNG/JPG of your ER diagram instead of using draw.io.
                        </Text>
                      </Stack>
                    </Paper>
                  </Stack>
                ) : null}

                {submissionMode === "drawio" ? (
                  <DrawioBoard
                    onExport={handleSubmitDrawioImage}
                    onExportError={(message) => setSubmitError(message)}
                    submitting={submitLoading || chatSending}
                  />
                ) : null}

                {submissionMode === "image" ? (
                  <Stack gap="xs">
                    <Dropzone
                      onDrop={(files) => setSubmissionImageFiles(files)}
                      onReject={(files) => console.log("Rejected submission image files", files)}
                      maxSize={5 * 1024 ** 2}
                      accept={IMAGE_MIME_TYPE}
                      multiple={false}
                      style={{
                        border: "2px dashed var(--mantine-color-blue-4)",
                        borderRadius: 12,
                        cursor: "pointer",
                        background: "var(--mantine-color-blue-0)",
                      }}
                    >
                      <Group justify="center" gap="xl" mih={180}>
                        <Dropzone.Accept>
                          <IconUpload size={52} color="var(--mantine-color-blue-6)" stroke={1.5} />
                        </Dropzone.Accept>
                        <Dropzone.Reject>
                          <IconX size={52} color="var(--mantine-color-red-6)" stroke={1.5} />
                        </Dropzone.Reject>
                        <Dropzone.Idle>
                          <IconPhoto size={52} color="var(--mantine-color-dimmed)" stroke={1.5} />
                        </Dropzone.Idle>
                        <div>
                          <Text size="xl" inline>
                            Drag image here or click to select
                          </Text>
                          <Text size="sm" c="dimmed" inline mt={7}>
                            Attach one image, up to 5 MB
                          </Text>
                        </div>
                      </Group>
                    </Dropzone>
                    {submissionImageFiles.length > 0 ? (
                      <Alert icon={<IconAlertCircle size={16} />} color="green" title="Image selected">
                        {submissionImageFiles[0]?.name}
                      </Alert>
                    ) : null}
                    <Group justify="flex-end">
                      <Button onClick={handleSubmitImage} loading={submitLoading} disabled={chatSending}>
                        Submit Diagram
                      </Button>
                    </Group>
                  </Stack>
                ) : null}

                {submitError ? (
                  <Alert icon={<IconAlertCircle size={16} />} color="red" title="Submission error">
                    {submitError}
                  </Alert>
                ) : null}

              </Stack>
            </Stack>
          </Box>
          <Box
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              setIsDragging(true);
              updateWidthFromPointer(event.clientX);
            }}
            onPointerMove={(event) => {
              if (!isDragging) return;
              updateWidthFromPointer(event.clientX);
            }}
            onPointerUp={(event) => {
              event.currentTarget.releasePointerCapture(event.pointerId);
              setIsDragging(false);
            }}
            style={{
              width: 14,
              cursor: "col-resize",
              background: "var(--mantine-color-gray-2)",
              position: "relative",
              flex: "0 0 8px",
              userSelect: "none",
              touchAction: "none",
            }}
          >
            <Box
              style={{
                position: "absolute",
                top: "25%",
                bottom: "25%",
                left: "50%",
                width: 3,
                transform: "translateX(-50%)",
                background: "var(--mantine-color-gray-6)",
                borderRadius: 2,
              }}
            />
          </Box>
          <Box
            style={{
              flex: "1 1 0",
              minWidth: 260,
              maxHeight: "100vh",
              background: "var(--mantine-color-body)",
              padding: 16,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <Tabs
              value={rightPanelTab}
              onChange={(value) => setRightPanelTab((value as "ai-chat" | "rubric") || "ai-chat")}
              style={{
                flex: 1,
                minHeight: 0,
                display: "flex",
                flexDirection: "column",
              }}
            >
              <Tabs.List>
                <Tabs.Tab value="ai-chat">AI Chat</Tabs.Tab>
                {showRubricTab ? <Tabs.Tab value="rubric">Rubric</Tabs.Tab> : null}
              </Tabs.List>

              <Tabs.Panel
                value="ai-chat"
                pt="sm"
                style={{
                  flex: 1,
                  minHeight: 0,
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <ChatPanel
                  onSendMessage={handleQuery}
                  injectedAssistantMessage={latestStudentMessage}
                  disabled={submitLoading}
                  onSendingChange={setChatSending}
                />
              </Tabs.Panel>

              {showRubricTab ? (
                <Tabs.Panel
                  value="rubric"
                  pt="sm"
                  style={{
                    flex: 1,
                    minHeight: 0,
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  <Stack gap="sm" style={{ flex: 1, minHeight: 0 }}>
                    <Title order={4}>Rubric</Title>
                    <ScrollArea
                      type="always"
                      offsetScrollbars
                      style={{
                        flex: 1,
                        minHeight: 0,
                        border: "1px solid var(--mantine-color-gray-3)",
                        borderRadius: 12,
                      }}
                      p="md"
                    >
                      <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
                        {question.rubric_md}
                      </Text>
                    </ScrollArea>
                  </Stack>
                </Tabs.Panel>
              ) : null}
            </Tabs>
          </Box>
        </Box>
      </Stack>
    </Container>
  );
}
