"use client";

import { useMemo, useState } from "react";
import {
  ActionIcon,
  Alert,
  Box,
  Button,
  Card,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { Dropzone, IMAGE_MIME_TYPE } from "@mantine/dropzone";
import { IconAlertCircle, IconArrowLeft, IconPhoto, IconUpload, IconX } from "@tabler/icons-react";
import { erDiagramService } from "@/services/er-diagram.service";
import { GenerateRubricDifficulty, GenerateRubricMode } from "@/types/er-diagram.types";
import styles from "./page.module.css";

export default function AddERDiagramQuestionPage() {
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [outputText, setOutputText] = useState("");
  const [rubricJson, setRubricJson] = useState<Record<string, unknown>>({});
  const [diffSummary, setDiffSummary] = useState<unknown[]>([]);
  const [difficulty, setDifficulty] = useState<GenerateRubricDifficulty | null>(null);
  const [problemTitle, setProblemTitle] = useState("");
  const [problemStatement, setProblemStatement] = useState("");
  const [refinementInstruction, setRefinementInstruction] = useState("");
  const [instructionHistory, setInstructionHistory] = useState<string[]>([]);
  const [modelAnswerFiles, setModelAnswerFiles] = useState<File[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [savedQuestionId, setSavedQuestionId] = useState<number | null>(null);
  const [savedSignature, setSavedSignature] = useState<string | null>(null);
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

  const currentSignature = useMemo(() => {
    const modelAnswerFile = modelAnswerFiles[0];
    return JSON.stringify({
      title: problemTitle.trim(),
      statement: problemStatement.trim(),
      rubric_md: outputText.trim(),
      rubric_json: rubricJson,
      difficulty,
      instruction_history: instructionHistory,
      model_answer_file: modelAnswerFile
        ? {
            name: modelAnswerFile.name,
            size: modelAnswerFile.size,
            type: modelAnswerFile.type,
            last_modified: modelAnswerFile.lastModified,
          }
        : null,
      diff_summary: diffSummary,
    });
  }, [problemTitle, problemStatement, outputText, rubricJson, difficulty, instructionHistory, modelAnswerFiles, diffSummary]);

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
        rubric_previous: mode === "patch" ? rubricJson : undefined,
        instruction_history: mode === "patch" ? nextHistory : undefined,
      });

      const rubricText = response.rubric_md;
      if (!rubricText.trim()) {
        throw new Error("Backend returned an empty rubric response");
      }

      setOutputText(rubricText);
      setRubricJson(response.rubric_json || {});
      setDiffSummary(response.diff_summary || []);
      setDifficulty(response.difficulty);
      setInstructionHistory(nextHistory);
      setIsSubmitted(true);
      setIsSaved(false);
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
    if (!outputText.trim()) {
      setError("Please generate rubrics before saving");
      return;
    }
    if (!difficulty) {
      setError("Difficulty metadata is missing from generated rubric");
      return;
    }
    if (savedSignature === currentSignature) {
      return;
    }

    setError(null);
    setIsSaving(true);

    try {
      const saved = await erDiagramService.saveQuestion({
        title: problemTitle.trim(),
        problem_statement: problemStatement.trim(),
        notation: "Chen",
        difficulty_label: difficulty.label,
        difficulty_rationale: difficulty.rationale,
        rubric_md: outputText.trim(),
        rubric_json: rubricJson,
        instruction_history: instructionHistory,
        model_answer: modelAnswerFiles[0] ?? null,
      });

      setIsSaved(true);
      setSavedQuestionId(saved.id);
      setSavedSignature(currentSignature);
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

  const saveDisabled = !outputText.trim() || !difficulty || isSaving || savedSignature === currentSignature;

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        <Group align="baseline" gap="sm">
          <ActionIcon
            component="a"
            href="/er-diagram"
            variant="subtle"
            size="sm"
            aria-label="Back to ER diagram list"
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

        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
          <Card withBorder padding="lg" radius="md">
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
                minRows={4}
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
                  <Group justify="center" gap="xl" mih={220} className={styles.dropzoneInner}>
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
              <Group justify="flex-end">
                {isSubmitted ? (
                  <Button
                    variant="light"
                    loading={isGenerating}
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

          <Card withBorder padding="lg" radius="md">
            <Stack gap="md" className={styles.outputStack}>
              <Text fw={500} size="sm">
                Rubrics Output
              </Text>
              {difficulty ? (
                <Alert color="blue" title={`Difficulty: ${difficulty.label}`}>
                  {difficulty.rationale}
                </Alert>
              ) : null}
              <Box className={styles.outputBox}>
                <Text c={outputText ? undefined : "dimmed"}>
                  {outputText || "Output will appear here."}
                </Text>
              </Box>
              {outputText ? (
                <Group justify="space-between" mt="auto">
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
        </SimpleGrid>
      </Stack>
    </Container>
  );
}