"use client";

import { useRef, useState } from "react";
import {
  ActionIcon,
  Alert,
  Box,
  Button,
  Container,
  Group,
  Paper,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Dropzone, IMAGE_MIME_TYPE } from "@mantine/dropzone";
import Link from "next/link";
import { IconAlertCircle, IconArrowLeft, IconPhoto, IconUpload, IconX } from "@tabler/icons-react";
import { ChatPanel } from "@/components/ChatPanel";
import { DrawioBoard } from "@/components/DrawioBoard";
import type { QuestionCardData } from "@/components/QuestionCard";
import { erDiagramService } from "@/services/er-diagram.service";
import type {
  ERSubmissionRequest,
  ERSubmissionResponse,
  ERSubmissionStreamEvent,
} from "@/types/er-diagram.types";

type WorkspaceProps = {
  question: QuestionCardData;
};

type SubmissionScore = {
  normalized_10?: number | string;
};

type SubmissionPayload = {
  score?: SubmissionScore;
  student_message?: string;
  [key: string]: unknown;
};

const parseSubmissionPayload = (
  structuredOutput: Record<string, unknown> | null | undefined,
  text: string | null | undefined,
): SubmissionPayload | null => {
  if (structuredOutput && Object.keys(structuredOutput).length > 0) {
    return structuredOutput as SubmissionPayload;
  }
  const raw = text?.trim();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as SubmissionPayload;
    }
  } catch {
    // Non-JSON submission text is expected in some workflows.
  }
  return null;
};

export function ERDiagramWorkspace({ question }: WorkspaceProps) {
  const [submissionMode, setSubmissionMode] = useState<"drawio" | "image" | null>(null);
  const [submissionImageFiles, setSubmissionImageFiles] = useState<File[]>([]);
  const [chatSending, setChatSending] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitResult, setSubmitResult] = useState<ERSubmissionResponse | null>(null);
  const [submitLiveText, setSubmitLiveText] = useState("");
  const [submitStructuredPreview, setSubmitStructuredPreview] = useState<Record<string, unknown> | null>(null);
  const [latestStudentMessage, setLatestStudentMessage] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [leftPercent, setLeftPercent] = useState(70);
  const [isDragging, setIsDragging] = useState(false);

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
    setSubmitResult(null);
    setSubmitLiveText("");
    setSubmitStructuredPreview(null);

    try {
      let finalResult: ERSubmissionResponse | null = null;
      for await (const event of erDiagramService.submitStream(payload)) {
        const typedEvent = event as ERSubmissionStreamEvent;
        if (typedEvent.event === "token") {
          setSubmitLiveText(typedEvent.data.text || "");
          continue;
        }
        if (typedEvent.event === "structured_output") {
          setSubmitStructuredPreview(typedEvent.data.structured_output || null);
          continue;
        }
        if (typedEvent.event === "done") {
          const payload = parseSubmissionPayload(typedEvent.data.structured_output, typedEvent.data.text);
          const studentMessage =
            typeof payload?.student_message === "string" ? payload.student_message.trim() : "";

          const normalizedResult: ERSubmissionResponse = {
            ...typedEvent.data,
            text: studentMessage || typedEvent.data.text || "",
            structured_output: (payload as Record<string, unknown> | null) || typedEvent.data.structured_output || null,
          };

          finalResult = normalizedResult;
          setSubmitLiveText(normalizedResult.text || "");
          setSubmitStructuredPreview(normalizedResult.structured_output || null);
          setSubmitResult(normalizedResult);
          if (studentMessage) {
            setLatestStudentMessage(studentMessage);
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
    } catch (err) {
      setSubmitError(getErrorMessage(err));
    } finally {
      setSubmitLoading(false);
    }
  };

  const resolvedPayload = parseSubmissionPayload(
    submitResult?.structured_output || submitStructuredPreview,
    submitResult?.text || submitLiveText,
  );
  const normalizedScore =
    typeof resolvedPayload?.score?.normalized_10 === "number"
      ? resolvedPayload.score.normalized_10
      : typeof resolvedPayload?.score?.normalized_10 === "string"
        ? Number(resolvedPayload.score.normalized_10)
        : null;

  const handleSubmitXml = async (xml: string) => {
    if (chatSending) return;
    const payloadXml = xml.trim();
    if (!payloadXml) {
      setSubmitError("Draw.io XML is empty. Please export from draw.io and try again.");
      return;
    }

    await runSubmitStream({
        question_id: question.id,
        mode: "Submit",
        submission_xml_text: payloadXml,
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
              <Group justify="space-between" align="center">
                <Title order={4}>Problem</Title>
                {normalizedScore !== null && Number.isFinite(normalizedScore) ? (
                  <Text fw={700} c="blue">
                    Score: {normalizedScore.toFixed(1)}/10
                  </Text>
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
                          Open the draw.io editor and submit using the exported XML.
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
                    onExport={handleSubmitXml}
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
            <ChatPanel
              onSendMessage={handleQuery}
              injectedAssistantMessage={latestStudentMessage}
              disabled={submitLoading}
              onSendingChange={setChatSending}
            />
          </Box>
        </Box>
      </Stack>
    </Container>
  );
}