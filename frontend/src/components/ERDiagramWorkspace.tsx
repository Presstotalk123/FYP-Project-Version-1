"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import { notifications } from "@mantine/notifications";
import { useRouter } from "next/navigation";
import { IconAlertCircle, IconArrowLeft, IconPhoto, IconUpload, IconX } from "@tabler/icons-react";
import { ChatPanel, type ChatHistoryMessage } from "@/components/ChatPanel";
import { DrawioBoard, type DrawioBoardHandle } from "@/components/DrawioBoard";
import { DrawioFocusLayout, type DrawioFocusLayoutHandle } from "@/components/DrawioFocusLayout";
import {
  buildRubricDisplayGroups,
  formatScoreValue,
  getRubricStatusMeta,
  summarizeRubricStatuses,
} from "@/utils/er-rubric-results";
import { erDiagramService } from "@/services/er-diagram.service";
import type {
  ERRubricJson,
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
  rubric_json: ERRubricJson | null;
  show_rubric_on_attempt: boolean;
};

export type LabContext = { er_lab_id: number; er_lab_question_id: number };

type WorkspaceProps = {
  question: ERDiagramWorkspaceQuestion;
  labContext?: LabContext;
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const normalizeSubmissionPayload = (value: unknown): ERSubmissionStructuredOutput | null => {
  if (!isObject(value)) return null;
  const score = value.score;
  const studentMessage = value.student_message;
  const checks = value.checks;
  if (!isObject(score)) return null;
  if (typeof studentMessage !== "string" || studentMessage.trim().length === 0) return null;
  if (!Array.isArray(checks)) return null;

  return {
    score: score as ERSubmissionStructuredOutput["score"],
    student_message: studentMessage,
    checks: checks as ERSubmissionStructuredOutput["checks"],
  };
};

const parseJsonObject = (value: unknown): Record<string, unknown> | null => {
  if (typeof value !== "string") return null;
  const raw = value.trim();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    return isObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const extractSubmissionPayload = (value: unknown): ERSubmissionStructuredOutput | null => {
  const directPayload = normalizeSubmissionPayload(value);
  if (directPayload) return directPayload;
  if (!isObject(value)) return null;

  const structuredPayload = extractSubmissionPayload(value.structured_output);
  if (structuredPayload) return structuredPayload;

  const answerPayload = extractSubmissionPayload(parseJsonObject(value.answer));
  if (answerPayload) return answerPayload;

  const textPayload = extractSubmissionPayload(parseJsonObject(value.text));
  if (textPayload) return textPayload;

  const messagePayload = extractSubmissionPayload(parseJsonObject(value.message));
  if (messagePayload) return messagePayload;

  return null;
};

const parseSubmissionPayload = (
  structuredOutput: unknown,
  text: string | null | undefined,
): ERSubmissionStructuredOutput | null => {
  return extractSubmissionPayload(structuredOutput) || extractSubmissionPayload(parseJsonObject(text));
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

const draftStorageKey = (questionId: number, labContext?: LabContext): string =>
  labContext ? `er-draft-lab-${labContext.er_lab_question_id}` : `er-draft-bank-${questionId}`;

const readDraftFromSessionStorage = (questionId: number, labContext?: LabContext): string => {
  if (typeof window === "undefined") return "";
  try {
    return window.sessionStorage.getItem(draftStorageKey(questionId, labContext)) ?? "";
  } catch {
    return "";
  }
};

export function ERDiagramWorkspace({ question, labContext }: WorkspaceProps) {
  const router = useRouter();
  const [submissionMode, setSubmissionMode] = useState<"drawio" | "image" | null>(null);
  const [submissionImageFiles, setSubmissionImageFiles] = useState<File[]>([]);
  const [chatSending, setChatSending] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [latestStudentMessage, setLatestStudentMessage] = useState<string | null>(null);
  const [latestStructuredOutput, setLatestStructuredOutput] = useState<ERSubmissionStructuredOutput | null>(null);
  const [hasSubmittedAttempt, setHasSubmittedAttempt] = useState(false);
  const [rightPanelTab, setRightPanelTab] = useState<"ai-chat" | "rubric">("ai-chat");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [leftPercent, setLeftPercent] = useState(70);
  const [isDragging, setIsDragging] = useState(false);
  const drawioRef = useRef<DrawioBoardHandle | null>(null);
  const focusLayoutRef = useRef<DrawioFocusLayoutHandle | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [initialDrawioXml] = useState(() => readDraftFromSessionStorage(question.id, labContext));
  const [chatHistory, setChatHistory] = useState<ChatHistoryMessage[] | null>(null);

  // Restore the persisted tutor transcript (LangGraph engine) so the chat log
  // survives reloads. Best-effort: no conversation yet / Dify engine / errors
  // all leave the chat empty, exactly as before.
  useEffect(() => {
    let cancelled = false;
    const ref = labContext
      ? { er_lab_id: labContext.er_lab_id, er_lab_question_id: labContext.er_lab_question_id }
      : { question_id: question.id };
    erDiagramService
      .getConversation(ref)
      .then((conversation) => {
        if (cancelled || !conversation.exists) return;
        const restored = conversation.messages
          .filter((m) => typeof m.content === "string" && m.content.trim().length > 0)
          .map((m) => ({
            id: String(m.id),
            role: m.role === "user" ? ("user" as const) : ("assistant" as const),
            content: (m.content as string).replace(/\\n/g, "\n"),
          }));
        if (restored.length > 0) setChatHistory(restored);
      })
      .catch(() => {
        // Transcript restore is a nicety — never block the workspace on it.
      });
    return () => {
      cancelled = true;
    };
    // Depend on primitives, not the labContext object identity, so a parent
    // re-render can't retrigger the fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.id, labContext?.er_lab_id, labContext?.er_lab_question_id]);
  const buildSubmissionRef = (): Pick<ERSubmissionRequest, "question_id" | "er_lab_id" | "er_lab_question_id"> =>
    labContext
      ? { er_lab_id: labContext.er_lab_id, er_lab_question_id: labContext.er_lab_question_id }
      : { question_id: question.id };

  const focusMode = submissionMode === "drawio";
  const showRubricTab = question.show_rubric_on_attempt && hasSubmittedAttempt;
  const latestScorePercent = useMemo(
    () => getSubmissionPercent(latestStructuredOutput),
    [latestStructuredOutput],
  );
  const rubricGroups = useMemo(
    () => buildRubricDisplayGroups(question.rubric_json, latestStructuredOutput),
    [question.rubric_json, latestStructuredOutput],
  );
  const rubricStatusCounts = useMemo(
    () => (rubricGroups ? summarizeRubricStatuses(rubricGroups).filter((item) => item.count > 0) : []),
    [rubricGroups],
  );

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
      ...buildSubmissionRef(),
      mode: "Query",
      student_query: message,
    });
    return response.text;
  };

  const runSubmitStream = async (payload: ERSubmissionRequest): Promise<void> => {
    setSubmitLoading(true);
    setSubmitError(null);

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
          const parsedStructuredOutput = parseSubmissionPayload(
            typedEvent.data.structured_output,
            typedEvent.data.text,
          );

          const normalizedResult: ERSubmissionResponse = {
            ...typedEvent.data,
            text: typedEvent.data.text || "",
            structured_output: parsedStructuredOutput || typedEvent.data.structured_output || null,
          };

          finalResult = normalizedResult;
          setLatestStructuredOutput(normalizedResult.structured_output);

          const studentMessage = parsedStructuredOutput?.student_message?.trim();
          if (studentMessage) {
            setLatestStudentMessage(studentMessage);
          } else if (typedEvent.data.text?.trim()) {
            setLatestStudentMessage(typedEvent.data.text.trim());
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
      try {
        if (typeof window !== "undefined") {
          window.sessionStorage.removeItem(draftStorageKey(question.id, labContext));
        }
      } catch {
        // ignore sessionStorage write failures
      }
      setIsDirty(false);
    } catch (err) {
      setSubmitError(getErrorMessage(err));
    } finally {
      setSubmitLoading(false);
    }
  };

  const handleAutosave = (xml: string) => {
    try {
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(draftStorageKey(question.id, labContext), xml);
      }
    } catch {
      // sessionStorage may throw QuotaExceededError; swallow silently
    }
    setIsDirty(true);
  };

  const persistDraft = (xml: string) => {
    try {
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(draftStorageKey(question.id, labContext), xml);
      }
    } catch {
      // ignore
    }
  };

  const downloadDrawioFile = (xml: string) => {
    if (typeof window === "undefined") return;
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
    const filename = `er-diagram-q${question.id}-${stamp}.drawio`;
    const blob = new Blob([xml], { type: "application/xml" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const saveXmlToFile = (xml: string) => {
    if (!xml) {
      notifications.show({
        color: "yellow",
        title: "Nothing to save",
        message: "Draw.io did not return any diagram XML.",
      });
      return;
    }
    try {
      downloadDrawioFile(xml);
      persistDraft(xml);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save diagram to file.";
      notifications.show({ color: "red", title: "Save failed", message });
    }
  };

  const handleSaveToFile = async () => {
    if (!drawioRef.current) return;
    try {
      const xml = await drawioRef.current.exportXml();
      saveXmlToFile(xml);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save diagram to file.";
      notifications.show({ color: "red", title: "Save failed", message });
    }
  };

  const handleLoadFromFile = (file: File) => {
    if (!drawioRef.current) return;
    const reader = new FileReader();
    reader.onerror = () => {
      notifications.show({
        color: "red",
        title: "Load failed",
        message: "Could not read the selected file.",
      });
    };
    reader.onload = () => {
      const xml = typeof reader.result === "string" ? reader.result : "";
      if (!xml.trim()) {
        notifications.show({
          color: "yellow",
          title: "Empty file",
          message: "The selected file does not contain any diagram XML.",
        });
        return;
      }
      if (isDirty) {
        const confirmed = window.confirm(
          "Replace current diagram with the file's contents? Unsaved canvas changes will be lost.",
        );
        if (!confirmed) return;
      }
      drawioRef.current?.loadXml(xml);
      persistDraft(xml);
      setIsDirty(true);
    };
    reader.readAsText(file);
  };

  const handleExitFocusMode = () => {
    setSubmissionMode(null);
  };

  const handleFocusSubmit = () => {
    if (chatSending || submitLoading) return;
    if (!drawioRef.current) {
      notifications.show({
        color: "red",
        title: "Diagram not ready",
        message: "Draw.io is still loading. Please try again in a moment.",
      });
      return;
    }
    setSubmitError(null);
    drawioRef.current.submit();
  };

  useEffect(() => {
    if (!focusMode || !submitError) return;
    notifications.show({
      color: "red",
      title: "Submission error",
      message: submitError,
    });
    setSubmitError(null);
  }, [focusMode, submitError]);

  const handleSubmitDrawioImage = async (imageFile: File) => {
    if (chatSending) return;
    if (!imageFile || imageFile.size === 0) {
      setSubmitError("Draw.io PNG export is empty. Please export again and retry.");
      return;
    }

    setSubmitError(null);

    await runSubmitStream({
        ...buildSubmissionRef(),
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
        ...buildSubmissionRef(),
        mode: "Submit",
        erd_img: image,
      });
  };

  const chatPanelNode: ReactNode = (
    <ChatPanel
      onSendMessage={handleQuery}
      injectedAssistantMessage={latestStudentMessage}
      disabled={submitLoading}
      onSendingChange={setChatSending}
      historyMessages={chatHistory}
    />
  );

  const rubricSectionNode: ReactNode = (
    <Stack gap="sm" style={{ flex: 1, minHeight: 0 }}>
      <Group justify="space-between" align="flex-start" gap="sm">
        <div>
          <Title order={4}>Rubric</Title>
          <Text size="sm" c="dimmed" mt={4}>
            Review each rubric item against your latest submission.
          </Text>
        </div>
      </Group>
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
        {rubricGroups ? (
          <Stack gap="lg">
            {latestStructuredOutput ? (
              <Paper withBorder radius="md" p="md">
                <Stack gap="xs">
                  <div>
                    <Text fw={600}>Latest submission summary</Text>
                    <Text size="sm" c="dimmed">
                      {formatScoreValue(latestStructuredOutput.score.earned_points)} /{" "}
                      {formatScoreValue(latestStructuredOutput.score.total_points)} points
                    </Text>
                  </div>
                  <Group gap="xs" wrap="wrap">
                    {rubricStatusCounts.map((item) => (
                      <Badge
                        key={item.status}
                        color={item.color}
                        radius="xl"
                        variant={item.status === "not_evaluated" ? "outline" : "light"}
                      >
                        {item.label}: {item.count}
                      </Badge>
                    ))}
                  </Group>
                </Stack>
              </Paper>
            ) : null}

            {rubricGroups.map((group) => (
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
                          <Badge variant="outline" color="blue" radius="xl">
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
          </Stack>
        ) : (
          <Stack gap="sm">
            <Alert color="gray" title="Structured rubric unavailable">
              This question does not have a structured rubric view yet. Showing the saved rubric text
              instead.
            </Alert>
            <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
              {question.rubric_md}
            </Text>
          </Stack>
        )}
      </ScrollArea>
    </Stack>
  );

  const problemDrawerContent: ReactNode = (
    <Stack gap="md">
      <Text style={{ whiteSpace: "pre-wrap" }}>{question.description}</Text>
      {latestStudentMessage ? (
        <Paper withBorder radius="md" p="md">
          <Stack gap={4}>
            <Text fw={600} size="sm">
              Latest submission feedback
            </Text>
            <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>
              {latestStudentMessage}
            </Text>
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  );

  if (focusMode) {
    return (
      <DrawioFocusLayout
        ref={focusLayoutRef}
        question={question}
        canvas={
          <DrawioBoard
            ref={drawioRef}
            onExport={handleSubmitDrawioImage}
            onExportError={(message) => setSubmitError(message)}
            submitting={submitLoading || chatSending}
            hideInternalSubmit
            initialXml={initialDrawioXml}
            onAutosave={handleAutosave}
            onSaveRequest={saveXmlToFile}
            onExitRequest={() => focusLayoutRef.current?.requestExit()}
          />
        }
        problemContent={problemDrawerContent}
        aiChatContent={chatPanelNode}
        rubricContent={rubricSectionNode}
        onSubmit={handleFocusSubmit}
        onSaveToFile={handleSaveToFile}
        onLoadFromFile={handleLoadFromFile}
        onExit={handleExitFocusMode}
        submitting={submitLoading || chatSending}
        scorePercent={latestScorePercent}
        hasSubmittedAttempt={hasSubmittedAttempt}
        showRubricToggle={showRubricTab}
        isDirty={isDirty}
      />
    );
  }

  return (
    <Container fluid px="sm" py="md">
      <Stack gap="md">
        <Group align="baseline" gap="sm">
          <ActionIcon
            onClick={() => router.back()}
            variant="subtle"
            size="sm"
            aria-label="Back to previous page"
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
            // sticky HeaderNav + Container py md + page-level Title group + Stack gap
            height: "calc(100vh - 160px)",
          }}
        >
          <Box
            style={{
              flex: `0 0 ${leftPercent}%`,
              minWidth: 320,
              background: "var(--mantine-color-body)",
              padding: 16,
              overflowY: "auto",
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
                {chatPanelNode}
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
                  {rubricSectionNode}
                </Tabs.Panel>
              ) : null}
            </Tabs>
          </Box>
        </Box>
      </Stack>
    </Container>
  );
}
