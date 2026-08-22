"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Alert,
  Badge,
  Box,
  Button,
  Container,
  Group,
  Image,
  Modal,
  Paper,
  ScrollArea,
  Stack,
  Tabs,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { Dropzone, IMAGE_MIME_TYPE } from "@mantine/dropzone";
import { notifications } from "@mantine/notifications";
import { useRouter } from "next/navigation";
import { IconAlertCircle, IconLogout, IconPhoto, IconUpload, IconX } from "@tabler/icons-react";
import { ChatPanel, TUTOR_NAME, type ChatHistoryMessage } from "@/components/ChatPanel";
import { DescriptionMarkdown } from "@/components/common/DescriptionMarkdown";
import { BalooAvatar } from "@/components/workspace/AiTutorAvatar";
import { QuestionWeightBadge } from "@/components/assessment/QuestionWeightBadge";
import { AssessmentTimer } from "@/components/assessment/AssessmentTimer";
import { QuestionNavigator } from "@/components/assessment/QuestionNavigator";
import { useAssessmentProgress } from "@/contexts/AssessmentProgressContext";
import { useAssessmentTimer } from "@/contexts/AssessmentTimerContext";
import { useAuth } from "@/contexts/AuthContext";
import { DrawioBoard, type DrawioBoardHandle } from "@/components/DrawioBoard";
import { DrawioFocusLayout, type DrawioFocusLayoutHandle } from "@/components/DrawioFocusLayout";
import drawioTheme from "@/components/DrawioTheme.module.css";
import {
  buildRubricDisplayGroups,
  formatScoreValue,
  getRubricStatusMeta,
  summarizeRubricStatuses,
} from "@/utils/er-rubric-results";
import { erDiagramService } from "@/services/er-diagram.service";
import { useErDraft } from "@/hooks/use-er-draft";
import { useErImageDraft } from "@/hooks/use-er-image-draft";
import { useErdGuideDismissed } from "@/hooks/use-erd-guide";
import { useBlockBrowserBack } from "@/hooks/use-block-browser-back";
import { useWarnBeforeUnload } from "@/hooks/use-warn-before-unload";
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

// Scoped brand-purple + Geist override for Mantine (DrawioTheme.module.css).
// Portalled components render outside this tree, so they carry the class too.
const BRAND_THEME_CLASS = drawioTheme.drawioTheme;

type WorkspaceProps = {
  question: ERDiagramWorkspaceQuestion;
  /** Assessment weightage (%) for this question; omitted outside assessments. */
  weight?: number;
  /** Where "Save and Exit" goes. Defaults to the pooled questions list; an
   *  assessment passes its overview. Mirrors SqlWorkspace's prop of the same
   *  name — a named destination rather than router.back(), which depends on how
   *  the student got here and lands anywhere after a refresh. */
  backUrl?: string;
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

// A draft push must never run concurrently with the grading stream (see
// confirmSubmitWithDescription), but it must also never be allowed to block
// one indefinitely. Losing a few seconds of draft sync is fully recoverable —
// the local copy still holds the work, and the next autosave retries — while
// losing the graded attempt to a stalled network call is not. A flush that
// genuinely completes fast (the common case) is unaffected: this only bites
// a pathological wait.
//
// This is deliberately shorter than er-diagram.service.ts's
// DRAFT_SAVE_TIMEOUT_MS (8s), not equal to it: giving up waiting on a slow
// draft PUT does not cancel the in-flight request itself, so with an 8s
// request timeout a draft write can still be outstanding for up to
// (DRAFT_SAVE_TIMEOUT_MS - FLUSH_BEFORE_SUBMIT_TIMEOUT_MS) ≈ 5s AFTER the SSE
// grading stream has already opened — technically overlapping it. That is
// acceptable, not a reintroduction of the bug this guards against: the
// grading endpoint commits and releases its pooled DB connection *before*
// the stream starts (see CLAUDE.md's ERD subsystem notes), so the real
// concern the invariant protects against — a write competing for a pooled
// connection for the stream's full 30-90s — never happens. The overlap here
// costs at most one extra connection for a few seconds at the very start,
// not for the life of the stream. (Shortening the request timeout to close
// this gap instead would be the wrong trade — 8s is the right forgiveness
// for a 500KB payload over a slow connection on the ordinary autosave path,
// which vastly outnumbers submit-time flushes.)
//
// The two constants are coupled — changing either one changes the size of
// this overlap — so reconsider both together, not just the one being edited.
const FLUSH_BEFORE_SUBMIT_TIMEOUT_MS = 3_000;

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

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

export function ERDiagramWorkspace({ question, weight, backUrl }: WorkspaceProps) {
  const router = useRouter();
  const progress = useAssessmentProgress();
  // Assessment countdown control. A no-op outside an assessment (practice/standalone), where the
  // provider isn't mounted and the context returns its safe default.
  const timer = useAssessmentTimer();
  useBlockBrowserBack(!!backUrl);
  useWarnBeforeUnload(!!backUrl);
  const [submissionMode, setSubmissionMode] = useState<"drawio" | "image" | null>(null);
  const [submissionImageFiles, setSubmissionImageFiles] = useState<File[]>([]);
  // Object URL for previewing the staged image (fresh drop or restored draft).
  // Recreated whenever the staged file changes and revoked on change/unmount so
  // a replace never leaks a blob URL.
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
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
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const draft = useErDraft({
    userId,
    questionId: question.id,
    // A conflict can resolve after draw.io has already initialized (its
    // `initialXml` prop only paints the canvas on the very first load
    // message); route adopted XML through the imperative handle too so it
    // reaches an already-mounted board.
    onAdoptXml: (xml) => drawioRef.current?.loadXml(xml),
  });
  // Restore an autosaved uploaded image into the dropzone. Only flips to image
  // mode from the untouched choice screen, so it never yanks a student out of an
  // active draw.io session or a mode they've already chosen this visit.
  const handleRestoreImage = useCallback((file: File) => {
    setSubmissionImageFiles([file]);
    setSubmissionMode((current) => (current === null ? "image" : current));
  }, []);
  const imageDraft = useErImageDraft({
    userId,
    questionId: question.id,
    onRestore: handleRestoreImage,
  });
  useEffect(() => {
    const file = submissionImageFiles[0];
    if (!file) {
      setImagePreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setImagePreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [submissionImageFiles]);
  const guide = useErdGuideDismissed(userId);
  const [chatHistory, setChatHistory] = useState<ChatHistoryMessage[] | null>(null);
  const [descModalOpen, setDescModalOpen] = useState(false);
  const [descText, setDescText] = useState("");
  const [pendingSubmitImage, setPendingSubmitImage] = useState<File | null>(null);
  // draw.io source captured alongside the PNG at submit time. The backend
  // parses it instead of running vision over the rendered image — the PNG is
  // generated from this XML, so the XML is exact where vision is a guess.
  // Null for image uploads, which keep the vision path.
  const [pendingSubmitXml, setPendingSubmitXml] = useState<string | null>(null);
  // Last XML draw.io autosaved, kept as the fallback source for a submission.
  const lastAutosavedXmlRef = useRef<string>("");
  // The uploaded-image File last successfully submitted, so the end-of-assessment
  // capture can skip re-grading an unchanged upload (uploads have no server draft to
  // diff against). Null until an image submission succeeds.
  const lastSubmittedImageRef = useRef<File | null>(null);

  // Restore the persisted tutor transcript (LangGraph engine) so the chat log
  // survives reloads. Best-effort: no conversation yet / Dify engine / errors
  // all leave the chat empty, exactly as before.
  useEffect(() => {
    let cancelled = false;
    erDiagramService
      .getConversation({ question_id: question.id })
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
        const restoredResult = extractSubmissionPayload(conversation.last_submit_report);
        if (restoredResult) {
          setLatestStructuredOutput(restoredResult);
          setHasSubmittedAttempt(true);
          progress.markAttempted();
          if (restoredResult.student_message?.trim()) {
            setLatestStudentMessage(restoredResult.student_message.trim());
          }
        }
      })
      .catch(() => {
        // Transcript restore is a nicety — never block the workspace on it.
      });
    return () => {
      cancelled = true;
    };
    // Deliberately keyed to the question alone — `progress` is a context helper
    // whose identity must not re-run the one-shot transcript restore.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.id]);
  // Inside an assessment, contribute this question's pending work to the end-of-assessment
  // capture the timer runs right before finalizing: flush the current canvas to its server
  // draft, and, if the student answered by uploading an image that hasn't been submitted
  // (or changed since), hand that image over — uploads aren't persisted server-side, so
  // this is the only chance to grade them. Re-registers when the staged answer changes so
  // the hook always sees the current image. registerPreFinalize / draft.flushNow are stable.
  const { registerPreFinalize } = timer;
  const flushNow = draft.flushNow;
  const imageFlushNow = imageDraft.flushNow;
  useEffect(() => {
    if (!backUrl) return;
    return registerPreFinalize(async () => {
      try {
        await flushNow();
      } catch {
        // The local copy still holds the work; never block finalize on a flush.
      }
      try {
        // Persist the staged image to its server draft so finalize can grade it
        // from server state (covers this AND any navigated-away question).
        await imageFlushNow();
      } catch {
        // Best-effort; the live handoff below is the race fallback.
      }
      // Hand over a staged image whenever one exists and hasn't been submitted, regardless
      // of the current submission mode: a student who drew in draw.io AND uploaded an image
      // should have both auto-submitted (the backend grades the XML draft and this image as
      // two attempts, best-of wins), so a leftover upload from before a mode switch is never
      // silently dropped.
      const staged = submissionImageFiles[0];
      if (staged && staged !== lastSubmittedImageRef.current) {
        return { imageQuestionId: question.id, image: staged };
      }
      return undefined;
    });
  }, [backUrl, submissionMode, submissionImageFiles, flushNow, imageFlushNow, question.id, registerPreFinalize]);

  const buildSubmissionRef = (): Pick<ERSubmissionRequest, "question_id"> => ({
    question_id: question.id,
  });

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

  const handleQuery = async (
    message: string,
    onToken?: (accumulatedText: string) => void,
  ): Promise<string> => {
    let accumulated = "";
    let finalText = "";
    for await (const event of erDiagramService.submitStream({
      ...buildSubmissionRef(),
      mode: "Query",
      student_query: message,
    })) {
      const typedEvent = event as ERSubmissionStreamEvent;
      if (typedEvent.event === "token") {
        accumulated = typedEvent.data.text || accumulated + (typedEvent.data.chunk || "");
        onToken?.(accumulated);
      } else if (typedEvent.event === "done") {
        finalText = typedEvent.data.text || accumulated;
      } else if (typedEvent.event === "error") {
        throw new Error(typedEvent.data.detail || "Query failed");
      }
    }
    return finalText || accumulated;
  };

  const runSubmitStream = async (payload: ERSubmissionRequest): Promise<void> => {
    setSubmitLoading(true);
    setSubmitError(null);
    // Freeze the assessment countdown while grading runs; the backend credits this time to the
    // deadline (like a SQL Run). resume() with no argument re-fetches the authoritative, now-
    // credited end_time — safe because the backend commits the credit before the stream closes.
    timer.pause();

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
      progress.markAttempted();
      // Remember a successfully-submitted upload so the end-of-assessment capture
      // doesn't re-grade it unchanged. An uploaded-image submission carries the image
      // but no XML; a draw.io submission always carries XML, so this never fires there.
      if (payload.erd_img && !payload.submission_xml_text) {
        lastSubmittedImageRef.current = payload.erd_img;
      }
      // The diagram stays the student's to keep working on — a submit is not an
      // eviction. It was already pushed up before the stream opened.
      setIsDirty(false);
      // Reveal the tutor's feedback now that the result is in. Deliberately
      // here and not when Submit is clicked: this only runs on the success
      // path, so a failed or interrupted submission leaves the panel alone
      // rather than opening it on nothing. No-op outside focus mode, where
      // the chat tab is already the default.
      focusLayoutRef.current?.openAiChat();
    } catch (err) {
      setSubmitError(getErrorMessage(err));
    } finally {
      setSubmitLoading(false);
      timer.resume();
    }
  };

  // Fired by draw.io on every change, now that the load message enables it.
  // Silent: no prompt, no download — the student never sees this happen.
  const handleAutosave = (xml: string) => {
    lastAutosavedXmlRef.current = xml;
    draft.recordChange(xml);
    setIsDirty(true);
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
      draft.recordChange(xml);
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
      draft.recordChange(xml);
      setIsDirty(true);
    };
    reader.readAsText(file);
  };

  const enterDrawioMode = () => {
    // `DrawioBoard` only lives inside the `focusMode` branch below, so this
    // mounts a brand new one, seeded from `initialXml={draft.initialXml}` at
    // whatever value that prop holds on the render that follows. Re-seed it
    // from the live canvas ref in the same tick (React batches these) so a
    // student who left and came back gets their last drawn content, not
    // whatever was true when the draft first reconciled at the original
    // mount.
    draft.syncInitialXml();
    setSubmissionMode("drawio");
  };

  const handleExitFocusMode = () => {
    void draft.flushNow();
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

  const requestSubmit = (imageFile: File, xml?: string | null) => {
    if (chatSending) return;
    if (!imageFile || imageFile.size === 0) {
      setSubmitError("Diagram export is empty. Please export again and retry.");
      return;
    }
    setSubmitError(null);
    setPendingSubmitImage(imageFile);
    setPendingSubmitXml(xml ?? null);
    setDescText("");
    setDescModalOpen(true);
  };

  const confirmSubmitWithDescription = async () => {
    const image = pendingSubmitImage;
    const xml = pendingSubmitXml;
    setDescModalOpen(false);
    if (!image) return;
    const description = descText.trim();
    setPendingSubmitImage(null);
    setPendingSubmitXml(null);
    // Disable the Submit control for the whole prepare-and-grade window, not
    // just once runSubmitStream's own setSubmitLoading(true) below runs — the
    // flush this triggers can take a few seconds (bounded, but not instant),
    // and leaving the button live until the stream actually opens let a
    // second click re-export the diagram and re-open this modal, triggering a
    // second graded run.
    setSubmitLoading(true);
    setSubmitError(null);
    // Push the exact XML being graded before the stream opens — a draft write
    // must never run concurrently with the 30-90s SSE grading connection.
    // Bounded: a flush that is still outstanding past a few seconds is
    // abandoned rather than awaited forever — the local copy still holds the
    // work either way, and losing a little draft sync is fully recoverable
    // where losing the graded attempt, while the assessment clock runs, is
    // not.
    if (xml?.trim()) {
      draft.recordChange(xml);
      await Promise.race([draft.flushNow(), sleep(FLUSH_BEFORE_SUBMIT_TIMEOUT_MS)]);
    }
    await runSubmitStream({
      ...buildSubmissionRef(),
      mode: "Submit",
      erd_img: image,
      submission_xml_text: xml || null,
      submission_description: description || null,
    });
  };

  const cancelSubmitDescription = () => {
    setDescModalOpen(false);
    setPendingSubmitImage(null);
    setPendingSubmitXml(null);
    setDescText("");
  };

  const handleSubmitDrawioImage = async (imageFile: File, xmlFromExport?: string) => {
    // The export reply normally carries the source next to the PNG, which is
    // the diagram the image was rendered from — exactly what we want to grade.
    // The two fallbacks only matter if draw.io omits it: ask for the XML
    // explicitly, then failing that use the last autosave. Losing the XML is
    // never fatal; the submission still goes through on the image alone.
    let xml: string | null = xmlFromExport?.trim() || null;
    if (!xml) {
      try {
        xml = drawioRef.current ? await drawioRef.current.exportXml() : null;
      } catch {
        xml = null;
      }
    }
    requestSubmit(imageFile, xml?.trim() || lastAutosavedXmlRef.current || null);
  };

  const handleSubmitImage = async () => {
    if (chatSending) return;
    const image = submissionImageFiles[0];
    if (!image) {
      setSubmitError("Please select an image before submitting.");
      return;
    }
    requestSubmit(image);
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
                          <Badge variant="outline" radius="xl">
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
      <DescriptionMarkdown content={question.description} />
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

  const descriptionModal: ReactNode = (
    <Modal
      opened={descModalOpen}
      onClose={cancelSubmitDescription}
      title="Describe your submission (optional)"
      centered
      classNames={{ root: BRAND_THEME_CLASS }}
    >
      <Text size="sm" c="dimmed" mb="sm">
        Add anything that helps the tutor read your diagram correctly (for
        example: which line is a relationship, which attribute is the key, or a
        cardinality that is hard to see). You can leave this blank.
      </Text>
      <Textarea
        value={descText}
        onChange={(e) => setDescText(e.currentTarget.value)}
        placeholder="e.g. The double line from Order to Contains means total participation."
        autosize
        minRows={3}
        maxRows={8}
        data-autofocus
      />
      <Group justify="flex-end" mt="md">
        <Button variant="default" onClick={cancelSubmitDescription} disabled={submitLoading}>
          Cancel
        </Button>
        <Button onClick={confirmSubmitWithDescription} loading={submitLoading}>
          Submit
        </Button>
      </Group>
    </Modal>
  );

  const conflictModal: ReactNode = (
    <Modal
      opened={draft.conflict !== null}
      onClose={() => {}}
      withCloseButton={false}
      closeOnClickOutside={false}
      closeOnEscape={false}
      title="Two versions of this diagram"
      centered
    >
      <Stack gap="md">
        <Text size="sm">
          This device has changes that never reached your account, and a newer version was
          saved from somewhere else. Keeping one does not delete the other from the device
          it is on.
        </Text>
        <Group justify="flex-end" gap="sm">
          <Button variant="default" onClick={() => draft.resolve("local")}>
            Keep this device&apos;s changes
          </Button>
          <Button onClick={() => draft.resolve("server")}>Load the newer version</Button>
        </Group>
      </Stack>
    </Modal>
  );

  if (focusMode) {
    return (
      <>
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
            initialXml={draft.initialXml}
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
        lastSavedAt={draft.lastSavedAt}
        saveState={draft.saveState}
        guideDismissed={guide.dismissed}
        onDismissGuideForever={guide.dismissForever}
      />
      {descriptionModal}
      {conflictModal}
      </>
    );
  }

  return (
    <Container fluid px="sm" py="md" className={BRAND_THEME_CLASS}>
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap">
          <Group align="baseline" gap="sm">
            <Title order={2}>{question.title}</Title>
            <Text c="dimmed" mt={4}>
              Difficulty: {question.difficulty}
            </Text>
            <AssessmentTimer />
            <QuestionWeightBadge weight={weight} />
          </Group>
          {/* Named "Save and Exit" like SqlWorkspace's, and like it this only
              navigates: the diagram is already on disk, written to the draft on
              every draw.io autosave. */}
          <Button
            leftSection={<IconLogout size={16} />}
            onClick={() => router.push(backUrl ?? "/student")}
            style={{ flexShrink: 0 }}
          >
            Save and Exit
          </Button>
        </Group>
        <QuestionNavigator />
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
            // Container py md + page-level Title group + Stack gap; the HeaderNav
            // itself is hidden in assessments (backUrl set) and adds another ~100px
            // of height to reclaim outside them.
            height: backUrl ? "calc(100vh - 60px)" : "calc(100vh - 160px)",
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
              <DescriptionMarkdown content={question.description} />

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
                      onClick={enterDrawioMode}
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
                      onDrop={(files) => {
                        setSubmissionImageFiles(files);
                        // Autosave immediately: cache in IndexedDB + upload to the
                        // server draft, so switching items or exiting never loses it.
                        if (files[0]) imageDraft.recordImage(files[0]);
                      }}
                      onReject={(files) => console.log("Rejected submission image files", files)}
                      maxSize={5 * 1024 ** 2}
                      accept={IMAGE_MIME_TYPE}
                      multiple={false}
                      style={{
                        border: "2px dashed var(--mantine-primary-color-3)",
                        borderRadius: 12,
                        cursor: "pointer",
                        background: "var(--mantine-primary-color-0)",
                      }}
                    >
                      <Group justify="center" gap="xl" mih={180}>
                        <Dropzone.Accept>
                          <IconUpload size={52} color="var(--mantine-primary-color-6)" stroke={1.5} />
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
                      <Stack gap="xs">
                        <Alert
                          icon={<IconAlertCircle size={16} />}
                          color="green"
                          title="Image selected"
                          withCloseButton
                          closeButtonLabel="Remove image"
                          onClose={() => {
                            setSubmissionImageFiles([]);
                            // Clear the autosaved draft (row + blob + local cache) so
                            // finalize grades nothing for a removed image.
                            imageDraft.removeImage();
                          }}
                        >
                          {submissionImageFiles[0]?.name}
                        </Alert>
                        {imagePreviewUrl ? (
                          <Paper withBorder radius="md" p="xs">
                            <Image
                              src={imagePreviewUrl}
                              alt={submissionImageFiles[0]?.name ?? "Uploaded ER diagram"}
                              fit="contain"
                              mah={220}
                              radius="sm"
                            />
                          </Paper>
                        ) : null}
                      </Stack>
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
                <Tabs.Tab value="ai-chat" leftSection={<BalooAvatar size={16} />}>
                  Ask {TUTOR_NAME}
                </Tabs.Tab>
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
      {descriptionModal}
      {conflictModal}
    </Container>
  );
}
