"use client";

import { useState } from "react";
import {
  ActionIcon,
  Alert,
  Box,
  Button,
  Card,
  Container,
  Grid,
  Group,
  Stack,
  Switch,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { Dropzone, IMAGE_MIME_TYPE } from "@mantine/dropzone";
import { IconAlertCircle, IconArrowLeft, IconPhoto, IconUpload, IconX } from "@tabler/icons-react";
import Editor from "@monaco-editor/react";
import { erDiagramService } from "@/services/er-diagram.service";
import type { ERRubricJson, GenerateRubricDifficulty, GenerateRubricMode } from "@/types/er-diagram.types";
import { formatRubricJson, isRubricJsonObject } from "@/utils/er-rubric-authoring";
import { buildRubricMarkdownFromJson } from "@/utils/er-rubric-markdown";
import { parseJsonObjectWithLocation } from "@/utils/json-parse-error";
import styles from "./page.module.css";

export default function AddERDiagramQuestionPage() {
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [rubricJson, setRubricJson] = useState<ERRubricJson>({});
  const [rubricJsonDraft, setRubricJsonDraft] = useState("{}");
  const [rubricJsonError, setRubricJsonError] = useState<string | null>(null);
  const [difficulty, setDifficulty] = useState<GenerateRubricDifficulty | null>(null);
  const [problemTitle, setProblemTitle] = useState("");
  const [problemStatement, setProblemStatement] = useState("");
  const [refinementInstruction, setRefinementInstruction] = useState("");
  const [instructionHistory, setInstructionHistory] = useState<string[]>([]);
  const [modelAnswerFiles, setModelAnswerFiles] = useState<File[]>([]);
  const [showRubricOnAttempt, setShowRubricOnAttempt] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [savedQuestionId, setSavedQuestionId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const getErrorMessage = (err: unknown): string => {
    const axiosErr = err as { response?: { data?: { detail?: unknown } }; message?: string };
    const detail = axiosErr.response?.data?.detail;

    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }

    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }
          if (item && typeof item === "object" && "msg" in item) {
            const msg = (item as { msg?: unknown }).msg;
            return typeof msg === "string" ? msg : null;
          }
          return null;
        })
        .filter((msg): msg is string => Boolean(msg && msg.trim()));

      if (messages.length > 0) {
        return messages.join("; ");
      }
    }

    if (detail && typeof detail === "object" && "msg" in detail) {
      const msg = (detail as { msg?: unknown }).msg;
      if (typeof msg === "string" && msg.trim()) {
        return msg;
      }
    }

    return axiosErr.message || "Unexpected request error";
  };

  const getDerivedRubricMarkdown = (value: ERRubricJson): string => buildRubricMarkdownFromJson(value);

  const commitJsonDraft = (): ERRubricJson | null => {
    const parsed = parseJsonObjectWithLocation(rubricJsonDraft, isRubricJsonObject, "rubric_json");
    if (!parsed.ok) {
      setRubricJsonError(parsed.message);
      return null;
    }

    setRubricJson(parsed.value);
    setRubricJsonError(null);
    setHasUnsavedChanges(true);
    return parsed.value;
  };

  const handleRubricJsonChange = (value: string) => {
    setRubricJsonDraft(value);
    const parsed = parseJsonObjectWithLocation(value, isRubricJsonObject, "rubric_json");
    setRubricJsonError(parsed.ok ? null : parsed.message);
  };

  const handleFormatJson = () => {
    const parsed = parseJsonObjectWithLocation(rubricJsonDraft, isRubricJsonObject, "rubric_json");
    if (!parsed.ok) return;
    setRubricJsonDraft(formatRubricJson(parsed.value));
  };

  const handleGenerateRubric = async (mode: GenerateRubricMode) => {
    if (!problemTitle.trim()) {
      setError("Problem title is required");
      return;
    }

    if (!problemStatement.trim()) {
      setError("Problem description is required");
      return;
    }

    const trimmedRefinement = refinementInstruction.trim();
    if (mode === "patch" && !trimmedRefinement) {
      setError("Refinement instructions are required for regenerate");
      return;
    }
    let committedRubricJson = rubricJson;
    if (mode === "patch") {
      const parsed = commitJsonDraft();
      if (!parsed) {
        setError("Please fix rubric_json before regenerating");
        return;
      }
      committedRubricJson = parsed;
    }
    if (mode === "patch" && rubricJsonError) {
      setError("Please fix rubric_json before regenerating");
      return;
    }

    setIsGenerating(true);
    setError(null);

    try {
      const nextHistory =
        mode === "create"
          ? trimmedRefinement
            ? [trimmedRefinement]
            : []
          : [...instructionHistory, trimmedRefinement];

      const response = await erDiagramService.generateRubric({
        mode,
        notation: "Chen",
        problem_title: problemTitle.trim(),
        problem_statement: problemStatement.trim(),
        model_answer: modelAnswerFiles[0] ?? null,
        refinement_instruction: trimmedRefinement || undefined,
        rubric_previous: mode === "patch" ? committedRubricJson : undefined,
        instruction_history: mode === "patch" ? nextHistory : undefined,
      });

      const nextRubricJson = response.rubric_json || {};
      if (!isRubricJsonObject(nextRubricJson)) {
        throw new Error("Backend returned an invalid rubric_json payload");
      }

      setRubricJson(nextRubricJson);
      setRubricJsonDraft(formatRubricJson(nextRubricJson));
      setRubricJsonError(null);
      setDifficulty(response.difficulty);
      setInstructionHistory(nextHistory);
      setIsSubmitted(true);
      setIsSaved(false);
      setHasUnsavedChanges(true);
      setSavedQuestionId(null);
      notifications.show({
        title: "Success",
        message: mode === "create" ? "Rubrics generated successfully" : "Rubrics regenerated successfully",
        color: "green",
      });
    } catch (err) {
      const message = getErrorMessage(err);
      setError(message);
      notifications.show({
        title: "Error",
        message,
        color: "red",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveRubric = async () => {
    if (!problemTitle.trim()) {
      setError("Problem title is required");
      return;
    }
    if (!problemStatement.trim()) {
      setError("Problem description is required");
      return;
    }
    if (Object.keys(rubricJson).length === 0) {
      setError("Please generate rubrics before saving");
      return;
    }
    if (!difficulty) {
      setError("Difficulty metadata is missing from generated rubric");
      return;
    }
    const parsed = commitJsonDraft();
    if (!parsed) {
      setError("Please fix rubric_json before saving");
      return;
    }
    const committedRubricJson = parsed;
    if (rubricJsonError) {
      setError("Please fix rubric_json before saving");
      return;
    }
    if (!hasUnsavedChanges) {
      return;
    }

    setError(null);
    setIsSaving(true);
    const derivedRubricMarkdown = getDerivedRubricMarkdown(committedRubricJson);

    try {
      const saved = await erDiagramService.saveQuestion({
        title: problemTitle.trim(),
        problem_statement: problemStatement.trim(),
        notation: "Chen",
        difficulty_label: difficulty.label,
        difficulty_rationale: difficulty.rationale,
        rubric_md: derivedRubricMarkdown,
        rubric_json: committedRubricJson,
        instruction_history: instructionHistory,
        show_rubric_on_attempt: showRubricOnAttempt,
        model_answer: modelAnswerFiles[0] ?? null,
      });

      setIsSaved(true);
      setSavedQuestionId(saved.id);
      setHasUnsavedChanges(false);
      notifications.show({
        title: "Saved",
        message: `Rubric saved as question #${saved.id}`,
        color: "green",
      });
    } catch (err) {
      const message = getErrorMessage(err);
      setError(message);
      notifications.show({
        title: "Error",
        message,
        color: "red",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const hasRubricJsonError = Boolean(rubricJsonError);
  const hasOutput = Object.keys(rubricJson).length > 0;
  const saveDisabled = !hasOutput || !difficulty || isSaving || hasRubricJsonError || !hasUnsavedChanges;

  return (
    <Container size="xl" py="xl">
      <Stack gap="lg">
        <Group align="baseline" gap="sm">
          <ActionIcon
            component="a"
            href="/problems"
            variant="subtle"
            size="sm"
            aria-label="Back to problems"
          >
            <IconArrowLeft size={18} />
          </ActionIcon>
          <div>
            <Title order={2}>Add ER Diagram Question</Title>
            <Text c="dimmed" mt={6}>
              Create a new ER diagram practice question.
            </Text>
          </div>
        </Group>

        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder padding="lg" radius="md" style={{ height: 720 }}>
            <Stack gap="md">
              {error ? (
                <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
                  {error}
                </Alert>
              ) : null}
              <Textarea
                label="Problem Title"
                placeholder="Title for the Problem"
                minRows={4}
                required
                value={problemTitle}
                onChange={(event) => setProblemTitle(event.currentTarget.value)}
              />
              <Textarea
                label="Problem description"
                placeholder="Describe the ER diagram problem here."
                rows={8}
                required
                value={problemStatement}
                onChange={(event) => setProblemStatement(event.currentTarget.value)}
              />
              <Stack gap={6}>
                <Group justify="space-between" align="center" gap="xs">
                  <Text fw={500} size="sm">
                    Model answer (image)
                  </Text>
                  <Text size="xs" c="dimmed">
                    (optional)
                  </Text>
                </Group>
                <Dropzone
                  className={styles.dropzoneRoot}
                  onDrop={(files) => setModelAnswerFiles(files)}
                  onReject={(files) => console.log("rejected files", files)}
                  maxSize={5 * 1024 ** 2}
                  accept={IMAGE_MIME_TYPE}
                  multiple={false}
                >
                  <Group justify="center" gap="xl" mih={110} className={styles.dropzoneInner}>
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
                        Drag images here or click to select files
                      </Text>
                      <Text size="sm" c="dimmed" inline mt={7}>
                        Attach an image, up to 5 MB
                      </Text>
                    </div>
                  </Group>
                </Dropzone>
                {modelAnswerFiles.length > 0 ? (
                  <Text size="sm" c="dimmed">
                    Selected: {modelAnswerFiles[0]?.name}
                  </Text>
                ) : null}
              </Stack>
              <Stack gap={6}>
                <Group justify="space-between" align="center" gap="xs">
                  <Text fw={500} size="sm">
                    Refinement Instructions
                  </Text>
                  <Text size="xs" c="dimmed">
                    (optional for first run, required for regenerate)
                  </Text>
                </Group>
                <Textarea
                  placeholder="List specific requirements or constraints."
                  minRows={3}
                  value={refinementInstruction}
                  onChange={(event) => setRefinementInstruction(event.currentTarget.value)}
                />
              </Stack>
              <Switch
                label="Show rubric to students after submission"
                description="When enabled, students can view the rubric in a separate tab after they submit their ERD."
                checked={showRubricOnAttempt}
                onChange={(event) => setShowRubricOnAttempt(event.currentTarget.checked)}
              />
              <Group justify="flex-end">
                {isSubmitted ? (
                  <Button
                    variant="light"
                    loading={isGenerating}
                    disabled={hasRubricJsonError}
                    onClick={() => handleGenerateRubric("patch")}
                  >
                    Regenerate Rubrics
                  </Button>
                ) : (
                  <Button
                    loading={isGenerating}
                    onClick={() => handleGenerateRubric("create")}
                  >
                    Submit
                  </Button>
                )}
              </Group>
            </Stack>
          </Card>
          </Grid.Col>

          <Grid.Col span={{ base: 12, md: 6 }}>
          <Card
            withBorder
            padding="lg"
            radius="md"
            style={{ display: "flex", flexDirection: "column", height: 720 }}
          >
            <Stack gap="md" className={styles.outputStack}>
              <Text fw={500} size="sm">
                Rubric Form
              </Text>
              <Text size="xs" c="dimmed">
                Edit the generated rubric JSON directly.
              </Text>
              {difficulty ? (
                <Alert color="blue" title={`Difficulty: ${difficulty.label}`}>
                  {difficulty.rationale}
                </Alert>
              ) : null}
              <Stack gap="xs" className={styles.jsonPanelStack}>
                {rubricJsonError ? (
                  <Alert color="red" title="Invalid rubric_json">
                    {rubricJsonError}
                  </Alert>
                ) : null}
                <Group justify="flex-end" gap="xs">
                  <Button
                    variant="subtle"
                    size="xs"
                    onClick={handleFormatJson}
                    disabled={!hasOutput || hasRubricJsonError || isGenerating || isSaving}
                  >
                    Format
                  </Button>
                </Group>
                <Box className={styles.jsonEditorWrapper}>
                  <Editor
                    height="100%"
                    language="json"
                    theme="light"
                    value={rubricJsonDraft}
                    onChange={(next) => handleRubricJsonChange(next ?? "")}
                    options={{
                      minimap: { enabled: false },
                      lineNumbers: "on",
                      fontSize: 13,
                      tabSize: 2,
                      wordWrap: "on",
                      formatOnPaste: true,
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                      readOnly: !hasOutput || isGenerating || isSaving,
                    }}
                  />
                </Box>
              </Stack>
              {hasOutput ? (
                <Group justify="space-between" style={{ marginTop: "auto" }}>
                  <Text size="xs" c={isSaved ? "green" : "dimmed"}>
                    {isSaved && savedQuestionId
                      ? `Saved as question #${savedQuestionId}`
                      : "Not saved"}
                  </Text>
                  <Button loading={isSaving} disabled={saveDisabled} onClick={handleSaveRubric}>
                    Save Rubrics
                  </Button>
                </Group>
              ) : null}
            </Stack>
          </Card>
          </Grid.Col>
        </Grid>
      </Stack>
    </Container>
  );
}
