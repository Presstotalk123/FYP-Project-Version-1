"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Card,
  Grid,
  Group,
  Stack,
  Switch,
  Text,
  Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { Dropzone, IMAGE_MIME_TYPE } from "@mantine/dropzone";
import { IconAlertCircle, IconPhoto, IconUpload, IconX } from "@tabler/icons-react";
import Editor from "@monaco-editor/react";
import { useAuth } from "@/contexts/AuthContext";
import { MarkdownDescriptionField } from "@/components/common/MarkdownDescriptionField";
import { erDiagramService } from "@/services/er-diagram.service";
import { queryKeys } from "@/services/query-keys";
import type {
  ERDiagramQuestion,
  ERRubricJson,
  GenerateRubricDifficulty,
  GenerateRubricMode,
} from "@/types/er-diagram.types";
import { formatRubricJson, isRubricJsonObject } from "@/utils/er-rubric-authoring";
import { buildRubricMarkdownFromJson } from "@/utils/er-rubric-markdown";
import { parseJsonObjectWithLocation } from "@/utils/json-parse-error";
import styles from "@/app/er-diagram/add/page.module.css";

/**
 * The ERD authoring surface, shared by create and edit — the same shape as
 * `QuestionForm` for SQL questions.
 *
 * Passing `question` switches it to edit mode: fields prefill from the saved
 * question, the generate button starts as "Regenerate Rubrics", and saving
 * issues a PUT instead of a POST.
 */
type ERQuestionFormProps = {
  /** Omit to create; supply to edit. */
  question?: ERDiagramQuestion;
};

export function ERQuestionForm({ question }: ERQuestionFormProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isStaff } = useAuth();
  const isEdit = Boolean(question);

  const initialRubric = (question?.rubric_json ?? {}) as ERRubricJson;

  const [isSubmitted, setIsSubmitted] = useState(isEdit);
  const [rubricJson, setRubricJson] = useState<ERRubricJson>(initialRubric);
  const [rubricJsonDraft, setRubricJsonDraft] = useState(
    isEdit ? formatRubricJson(initialRubric) : "{}",
  );
  const [rubricJsonError, setRubricJsonError] = useState<string | null>(null);
  const [difficulty, setDifficulty] = useState<GenerateRubricDifficulty | null>(
    question ? { label: question.difficulty_label, rationale: question.difficulty_rationale } : null,
  );
  const [problemTitle, setProblemTitle] = useState(question?.title ?? "");
  const [problemStatement, setProblemStatement] = useState(question?.problem_statement ?? "");
  const [refinementInstruction, setRefinementInstruction] = useState("");
  const [instructionHistory, setInstructionHistory] = useState<string[]>(
    question?.instruction_history ?? [],
  );
  const [modelAnswerFiles, setModelAnswerFiles] = useState<File[]>([]);
  const [showRubricOnAttempt, setShowRubricOnAttempt] = useState(
    question?.show_rubric_on_attempt ?? false,
  );
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [savedQuestionId, setSavedQuestionId] = useState<number | null>(null);

  const attemptCount = question?.attempt_count ?? 0;

  // Validation and API errors surface as toasts, not an inline Alert: an Alert
  // inside the form card shifts every control below it down mid-edit. The
  // "Already attempted" warning sits outside that card for the same reason.
  const showErrorNotification = (message: string) =>
    notifications.show({ title: "Error", message, color: "red" });

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

  // Every edit path marks the form dirty. Gating this on regeneration alone is
  // what made the old lab question editor impossible to save from.
  const handleRubricJsonChange = (value: string) => {
    setRubricJsonDraft(value);
    setHasUnsavedChanges(true);
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
      showErrorNotification("Problem title is required");
      return;
    }

    if (!problemStatement.trim()) {
      showErrorNotification("Problem description is required");
      return;
    }

    const trimmedRefinement = refinementInstruction.trim();
    if (mode === "patch" && !trimmedRefinement) {
      showErrorNotification("Refinement instructions are required for regenerate");
      return;
    }
    let committedRubricJson = rubricJson;
    if (mode === "patch") {
      const parsed = commitJsonDraft();
      if (!parsed) {
        showErrorNotification("Please fix rubric_json before regenerating");
        return;
      }
      committedRubricJson = parsed;
    }
    if (mode === "patch" && rubricJsonError) {
      showErrorNotification("Please fix rubric_json before regenerating");
      return;
    }

    setIsGenerating(true);

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
      showErrorNotification(getErrorMessage(err));
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveRubric = async () => {
    if (!problemTitle.trim()) {
      showErrorNotification("Problem title is required");
      return;
    }
    if (!problemStatement.trim()) {
      showErrorNotification("Problem description is required");
      return;
    }
    if (Object.keys(rubricJson).length === 0) {
      showErrorNotification("Please generate rubrics before saving");
      return;
    }
    if (!difficulty) {
      showErrorNotification("Difficulty metadata is missing from generated rubric");
      return;
    }
    const parsed = commitJsonDraft();
    if (!parsed) {
      showErrorNotification("Please fix rubric_json before saving");
      return;
    }
    const committedRubricJson = parsed;
    if (rubricJsonError) {
      showErrorNotification("Please fix rubric_json before saving");
      return;
    }

    // Students graded against the current rubric keep their old scores, so make
    // the author aware before the rubric moves under them.
    if (isEdit && attemptCount > 0) {
      const confirmed = window.confirm(
        `${attemptCount} student${attemptCount === 1 ? " has" : "s have"} already been graded ` +
          `against the current rubric. Their scores will not be recalculated. Save anyway?`,
      );
      if (!confirmed) return;
    }

    setIsSaving(true);
    const derivedRubricMarkdown = getDerivedRubricMarkdown(committedRubricJson);

    const payload = {
      title: problemTitle.trim(),
      problem_statement: problemStatement.trim(),
      notation: "Chen" as const,
      difficulty_label: difficulty.label,
      difficulty_rationale: difficulty.rationale,
      rubric_md: derivedRubricMarkdown,
      rubric_json: committedRubricJson,
      instruction_history: instructionHistory,
      show_rubric_on_attempt: showRubricOnAttempt,
      model_answer: modelAnswerFiles[0] ?? null,
    };

    try {
      if (isEdit && question) {
        const saved = await erDiagramService.updateQuestion(question.id, payload);
        notifications.show({
          title: "Saved",
          message: `Question #${saved.id} updated`,
          color: "green",
        });
        // refetchType 'all' is required: the query client sets refetchOnMount
        // false, so a plain invalidate would leave the unmounted lists stale.
        await queryClient.invalidateQueries({ queryKey: queryKeys.erdQuestions, refetchType: "all" });
        router.push("/admin/problems");
        return;
      }

      const saved = await erDiagramService.saveQuestion(payload);
      setIsSaved(true);
      setSavedQuestionId(saved.id);
      setHasUnsavedChanges(false);
      notifications.show({
        title: "Saved",
        message: `Rubric saved as question #${saved.id}`,
        color: "green",
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.erdQuestions, refetchType: "all" });
      router.push(isStaff ? "/admin/problems" : "/student");
    } catch (err) {
      showErrorNotification(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const hasRubricJsonError = Boolean(rubricJsonError);
  const hasOutput = Object.keys(rubricJson).length > 0;
  const saveDisabled = !hasOutput || !difficulty || isSaving || hasRubricJsonError || !hasUnsavedChanges;

  return (
    <Grid gutter="lg">
      {/* Full width, above both cards: inside the form card it pushed the
          controls at the bottom — refinement box, switch, Submit — out of view. */}
      {isEdit && attemptCount > 0 ? (
        <Grid.Col span={12}>
          <Alert icon={<IconAlertCircle size={16} />} color="yellow" title="Already attempted">
            {attemptCount} student{attemptCount === 1 ? " has" : "s have"} been graded against the
            current rubric. Editing it will not recalculate their scores.
          </Alert>
        </Grid.Col>
      ) : null}
      <Grid.Col span={{ base: 12, md: 6 }}>
        {/* No fixed height: the row grows to whatever the fields need, so the
            form never scrolls and never clips. It has to grow — the description
            field can be dragged taller and swaps to a Preview pane of unknown
            length, so no height chosen here would hold. `height: 100%` only
            keeps the card level with the editor opposite when the editor's
            min-height is the taller of the two. */}
        <Card withBorder padding="lg" radius="md" style={{ height: "100%" }}>
          <Stack gap="md">
            <Textarea
              label="Problem Title"
              placeholder="Title for the Problem"
              minRows={4}
              required
              value={problemTitle}
              onChange={(event) => {
                setProblemTitle(event.currentTarget.value);
                setHasUnsavedChanges(true);
              }}
            />
            <MarkdownDescriptionField
              id="er-problem-description"
              label="Problem description"
              placeholder="Describe the ER diagram problem here."
              minHeight={180}
              required
              value={problemStatement}
              onChange={(value) => {
                setProblemStatement(value);
                setHasUnsavedChanges(true);
              }}
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
              {question?.model_answer_storage_key ? (
                <Text size="xs" c="dimmed">
                  Current model answer: <code>{question.model_answer_storage_key}</code>. Upload a
                  new file to replace it; leave empty to keep.
                </Text>
              ) : null}
              <Dropzone
                className={styles.dropzoneRoot}
                onDrop={(files) => {
                  setModelAnswerFiles(files);
                  setHasUnsavedChanges(true);
                }}
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
              onChange={(event) => {
                setShowRubricOnAttempt(event.currentTarget.checked);
                setHasUnsavedChanges(true);
              }}
            />
            <Group justify="flex-end">
              {/* Leaves by the same door a successful save does, so abandoning a
                  question and finishing one land in the same place. Matches the
                  SQL QuestionForm, where Cancel sits beside the submit button
                  rather than being an arrow up in the page heading. */}
              <Button
                variant="default"
                onClick={() => router.push(isStaff ? "/admin/problems" : "/student")}
                disabled={isGenerating || isSaving}
              >
                Cancel
              </Button>
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
                <Button loading={isGenerating} onClick={() => handleGenerateRubric("create")}>
                  Submit
                </Button>
              )}
            </Group>
          </Stack>
        </Card>
      </Grid.Col>

      {/* `height: 100%` fills the row, which Grid stretches to the form card
          beside it, so the two stay level whatever the form's height is. The
          min-height is the floor for the stacked mobile layout, where there is
          no taller sibling to stretch against and 100% has nothing to resolve
          against — without it Monaco would collapse to zero. */}
      <Grid.Col span={{ base: 12, md: 6 }}>
        <Card
          withBorder
          padding="lg"
          radius="md"
          style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 720 }}
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
                  {isEdit ? "Save Changes" : "Save Rubrics"}
                </Button>
              </Group>
            ) : null}
          </Stack>
        </Card>
      </Grid.Col>
    </Grid>
  );
}
