"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Group,
  Menu,
  Modal,
  Stack,
  Text,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconDeviceFloppy,
  IconFileImport,
  IconFolder,
  IconHelpCircle,
  IconNotebook,
  IconReportAnalytics,
  IconX,
} from "@tabler/icons-react";
import type { ERDiagramWorkspaceQuestion } from "@/components/ERDiagramWorkspace";
import type { DraftSaveState } from "@/hooks/use-er-draft";
import { TUTOR_NAME } from "@/components/ChatPanel";
import { BalooAvatar } from "@/components/workspace/AiTutorAvatar";
import { IconBear } from "@/components/workspace/IconBear";
import { ErdGuideModal } from "@/components/ErdGuideModal";
import { AssessmentTimer } from "@/components/assessment/AssessmentTimer";
import drawioTheme from "@/components/DrawioTheme.module.css";

type DrawioFocusLayoutProps = {
  question: ERDiagramWorkspaceQuestion;
  canvas: ReactNode;
  problemContent: ReactNode;
  aiChatContent: ReactNode;
  rubricContent: ReactNode;
  onSubmit: () => void;
  /** May be async — the exit flow awaits it before tearing down the canvas. */
  onSaveToFile: () => void | Promise<void>;
  onLoadFromFile: (file: File) => void;
  onExit: () => void;
  submitting: boolean;
  scorePercent: number | null;
  hasSubmittedAttempt: boolean;
  showRubricToggle: boolean;
  isDirty: boolean;
  /** Epoch ms of the last auto-save, or null if nothing is stored yet. */
  lastSavedAt: number | null;
  saveState: DraftSaveState;
  /**
   * Whether the student has chosen "Don't remind me again" for the guide.
   * Until then the guide opens on its own each time focus mode is entered.
   */
  guideDismissed: boolean;
  onDismissGuideForever: () => void;
};

type RightPanel = "chat" | "rubric" | null;

/** Which side panel a drag is currently resizing, if any. */
type ResizingSide = "problem" | "right" | null;

export type DrawioFocusLayoutHandle = {
  requestExit: () => void;
  /** Reveal Baloo's chat panel — used to surface tutor feedback on submit. */
  openAiChat: () => void;
};

const TOOLBAR_HEIGHT = 48;
const PILL_WIDTH = 104;

// Panel sizing, shared by the left (Problem) and right (Baloo / Rubric)
// panels so both resize with identical feel.
const PANEL_MIN_WIDTH = 280;
const PANEL_MAX_FRACTION = 0.6;
// Drag narrower than this and the panel closes, rather than leaving a sliver.
const PANEL_COLLAPSE_WIDTH = 150;

// Scoped brand-purple + Geist override for Mantine (DrawioTheme.module.css).
// Portalled components render outside this tree, so they carry the class too.
const BRAND_THEME_CLASS = drawioTheme.drawioTheme;

/**
 * A switch, not a nested ternary, so `lastSavedAt` can only be consulted
 * inside the `"synced"` branch. A ternary chain that falls through to
 * `lastSavedAt ? "Saved …" : "Not auto-saved yet"` as its default reads
 * "saved" for `"idle"` too — `recordChange` sets `lastSavedAt` on every
 * local write, before any network request exists — which is exactly the
 * falsehood this feature exists to remove. Keeping the two states apart
 * structurally (rather than via a condition someone could later loosen)
 * is the point.
 */
function autosaveStatusText(saveState: DraftSaveState, lastSavedAt: number | null): string {
  switch (saveState) {
    case "saving":
      return "Saving…";
    case "local-only":
      return "Saved on this device only";
    case "too-large":
      return "Too large to sync — saved on this device";
    case "storage-full":
      return "Device storage full — not saved";
    case "synced":
      return lastSavedAt
        ? `Saved ${new Date(lastSavedAt).toLocaleTimeString()}`
        : "Not auto-saved yet";
    case "idle":
      return "Not auto-saved yet";
  }
}

export const DrawioFocusLayout = forwardRef<DrawioFocusLayoutHandle, DrawioFocusLayoutProps>(
  function DrawioFocusLayout(
    {
      question,
      canvas,
      problemContent,
      aiChatContent,
      rubricContent,
      onSubmit,
      onSaveToFile,
      onLoadFromFile,
      onExit,
      submitting,
      scorePercent,
      hasSubmittedAttempt,
      showRubricToggle,
      isDirty,
      lastSavedAt,
      saveState,
      guideDismissed,
      onDismissGuideForever,
    },
    ref,
  ) {
  const [problemOpen, setProblemOpen] = useState(false);
  const [problemWidth, setProblemWidth] = useState(400);
  const [rightWidth, setRightWidth] = useState(420);
  const [resizing, setResizing] = useState<ResizingSide>(null);
  const [rightPanel, setRightPanel] = useState<RightPanel>(null);
  const [exitConfirmOpen, setExitConfirmOpen] = useState(false);
  const [savingBeforeExit, setSavingBeforeExit] = useState(false);
  // Initial value only: this layout mounts fresh on every entry into focus
  // mode, so "open unless dismissed" is evaluated exactly then. Later changes
  // to `guideDismissed` come from the guide's own button, which closes it too.
  const [guideOpen, setGuideOpen] = useState(!guideDismissed);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const startResizing = useCallback((side: Exclude<ResizingSide, null>) => (e: React.MouseEvent) => {
    e.preventDefault();
    setResizing(side);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    if (!resizing) return;

    const releaseCursor = () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    const handleMouseMove = (e: MouseEvent) => {
      // The right panel grows as the pointer moves left, so measure it from the
      // viewport's right edge; the left panel measures straight from clientX.
      const newWidth = resizing === "problem" ? e.clientX : window.innerWidth - e.clientX;

      if (newWidth < PANEL_COLLAPSE_WIDTH) {
        if (resizing === "problem") {
          setProblemOpen(false);
        } else {
          setRightPanel(null);
        }
        setResizing(null);
        releaseCursor();
        return;
      }

      const clamped = Math.min(
        Math.max(newWidth, PANEL_MIN_WIDTH),
        window.innerWidth * PANEL_MAX_FRACTION,
      );
      if (resizing === "problem") {
        setProblemWidth(clamped);
      } else {
        setRightWidth(clamped);
      }
    };

    const handleMouseUp = () => {
      setResizing(null);
      releaseCursor();
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      releaseCursor();
    };
  }, [resizing]);

  const visibleRightPanel: RightPanel =
    rightPanel === "rubric" && !showRubricToggle ? null : rightPanel;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const isSaveCombo =
        (event.ctrlKey || event.metaKey) &&
        !event.shiftKey &&
        !event.altKey &&
        (event.key === "s" || event.key === "S");
      if (!isSaveCombo) return;
      event.preventDefault();
      onSaveToFile();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onSaveToFile]);

  const handleExitClick = useCallback(() => {
    if (isDirty) {
      setExitConfirmOpen(true);
      return;
    }
    onExit();
  }, [isDirty, onExit]);

  useImperativeHandle(
    ref,
    () => ({
      requestExit: handleExitClick,
      openAiChat: () => setRightPanel("chat"),
    }),
    [handleExitClick],
  );

  const handleConfirmSaveAndExit = async () => {
    // Must await: onSaveToFile() round-trips to the draw.io iframe for the
    // diagram XML. Exiting first unmounts DrawioBoard and its postMessage
    // listener, so the reply would be dropped and no file ever written.
    setSavingBeforeExit(true);
    try {
      await onSaveToFile();
    } finally {
      setSavingBeforeExit(false);
    }
    setExitConfirmOpen(false);
    onExit();
  };

  const handleConfirmDiscardAndExit = () => {
    setExitConfirmOpen(false);
    onExit();
  };

  const toggleRightPanel = (next: Exclude<RightPanel, null>) => {
    setRightPanel((current) => (current === next ? null : next));
  };

  const handleDismissGuideForever = () => {
    onDismissGuideForever();
    setGuideOpen(false);
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      onLoadFromFile(file);
    }
  };

  return (
    <Box
      className={BRAND_THEME_CLASS}
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--mantine-color-body)",
        display: "flex",
        flexDirection: "column",
        zIndex: 100,
      }}
    >
      <Box
        component="header"
        style={{
          height: TOOLBAR_HEIGHT,
          flexShrink: 0,
          borderBottom: "1px solid var(--mantine-color-gray-3)",
          background: "var(--mantine-color-body)",
          paddingInline: 12,
          display: "flex",
          alignItems: "center",
          gap: 8,
          position: "relative",
        }}
      >
        <Tooltip label="Exit focus mode" withArrow className={BRAND_THEME_CLASS}>
          <ActionIcon
            variant="subtle"
            size="lg"
            aria-label="Exit focus mode"
            onClick={handleExitClick}
          >
            <IconArrowLeft size={18} />
          </ActionIcon>
        </Tooltip>

        <Group gap={6} ml="sm">
          <Menu shadow="md" position="bottom-start" withinPortal>
            <Menu.Target>
              <Button
                size="xs"
                variant="light"
                leftSection={<IconFolder size={14} />}
                w={PILL_WIDTH}
              >
                File
              </Button>
            </Menu.Target>
            <Menu.Dropdown className={BRAND_THEME_CLASS}>
              <Menu.Item
                leftSection={<IconDeviceFloppy size={14} />}
                onClick={onSaveToFile}
              >
                Save to file (Ctrl+S)
              </Menu.Item>
              <Menu.Item
                leftSection={<IconFileImport size={14} />}
                onClick={() => fileInputRef.current?.click()}
              >
                Load from file…
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
          <Button
            size="xs"
            variant={problemOpen ? "filled" : "light"}
            leftSection={<IconNotebook size={14} />}
            onClick={() => setProblemOpen((open) => !open)}
            w={PILL_WIDTH}
          >
            Problem
          </Button>
          <Button
            size="xs"
            variant={visibleRightPanel === "chat" ? "filled" : "light"}
            leftSection={<IconBear size={14} />}
            onClick={() => toggleRightPanel("chat")}
            w={PILL_WIDTH}
          >
            {TUTOR_NAME}
          </Button>
          {showRubricToggle ? (
            <Button
              size="xs"
              variant={visibleRightPanel === "rubric" ? "filled" : "light"}
              leftSection={<IconReportAnalytics size={14} />}
              onClick={() => toggleRightPanel("rubric")}
              w={PILL_WIDTH}
            >
              Rubric
            </Button>
          ) : null}
        </Group>

        <Box style={{ flex: 1 }} />

        <AssessmentTimer />

        <Tooltip label="How to draw and submit" withArrow className={BRAND_THEME_CLASS}>
          <ActionIcon
            variant={guideOpen ? "light" : "subtle"}
            size="lg"
            aria-label="How to draw and submit your ER diagram"
            onClick={() => setGuideOpen((open) => !open)}
            mr={4}
            data-testid="erd-guide-toggle"
          >
            <IconHelpCircle size={20} />
          </ActionIcon>
        </Tooltip>

        <Box
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            transform: "translate(-50%, -50%)",
            pointerEvents: "none",
            maxWidth: "40%",
          }}
        >
          <Text fw={600} size="sm" lineClamp={1} ta="center">
            {question.title}
          </Text>
        </Box>

        <Text
          size="xs"
          c={
            saveState === "local-only" ||
            saveState === "too-large" ||
            saveState === "storage-full"
              ? "yellow.7"
              : "dimmed"
          }
          mr="sm"
          data-testid="autosave-status"
        >
          {autosaveStatusText(saveState, lastSavedAt)}
        </Text>

        {scorePercent !== null ? (
          <Badge color="green" variant="light" size="lg">
            Score: {scorePercent}%
          </Badge>
        ) : null}

        <Button size="xs" onClick={onSubmit} loading={submitting}>
          Submit
        </Button>
      </Box>

      <Box style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "row", position: "relative" }}>
        {problemOpen && (
          <Box
            style={{
              width: problemWidth,
              flexShrink: 0,
              background: "var(--mantine-color-body)",
              borderRight: "1px solid var(--mantine-color-gray-3)",
              display: "flex",
              flexDirection: "column",
              zIndex: 10,
            }}
          >
            <Box style={{ padding: "12px 16px", borderBottom: "1px solid var(--mantine-color-gray-3)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <Group gap="xs" align="center">
                <Text fw={600}>Problem</Text>
                <Badge variant="light" size="sm">
                  {question.difficulty}
                </Badge>
              </Group>
              <ActionIcon onClick={() => setProblemOpen(false)} size="sm" variant="subtle">
                <IconX size={16} />
              </ActionIcon>
            </Box>
            <Box style={{ padding: 16, overflowY: "auto", flex: 1 }}>
              {problemContent}
            </Box>
          </Box>
        )}

        {problemOpen && (
          <Box
            onMouseDown={startResizing("problem")}
            style={{
              width: 12,
              cursor: "col-resize",
              zIndex: 11,
              position: "absolute",
              left: problemWidth - 6,
              top: 0,
              bottom: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Box
              style={{
                width: 4,
                height: 32,
                borderRadius: 4,
                background:
                  resizing === "problem"
                    ? "var(--mantine-primary-color-filled)"
                    : "var(--mantine-color-gray-4)",
                transition: "background-color 0.2s",
              }}
            />
          </Box>
        )}

        <Box style={{ flex: 1, minWidth: 0, position: "relative" }}>
          {canvas}
          {/* The canvas is a cross-origin iframe, which swallows pointer events
              mid-drag. This catches them so a resize can start over the canvas
              and keep tracking once the pointer moves across it. */}
          {resizing && <Box style={{ position: "absolute", inset: 0, zIndex: 999 }} />}
        </Box>

        {visibleRightPanel !== null && (
          <Box
            onMouseDown={startResizing("right")}
            style={{
              width: 12,
              cursor: "col-resize",
              zIndex: 11,
              position: "absolute",
              right: rightWidth - 6,
              top: 0,
              bottom: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Box
              style={{
                width: 4,
                height: 32,
                borderRadius: 4,
                background:
                  resizing === "right"
                    ? "var(--mantine-primary-color-filled)"
                    : "var(--mantine-color-gray-4)",
                transition: "background-color 0.2s",
              }}
            />
          </Box>
        )}

        {/* Always mounted, hidden with display:none rather than unmounted — this
            is what the Drawer's `keepMounted` used to give us, and it keeps the
            AI chat's messages and half-typed input alive across toggles. */}
        <Box
          style={{
            width: rightWidth,
            flexShrink: 0,
            background: "var(--mantine-color-body)",
            borderLeft: "1px solid var(--mantine-color-gray-3)",
            display: visibleRightPanel === null ? "none" : "flex",
            flexDirection: "column",
            zIndex: 10,
          }}
        >
          <Box
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid var(--mantine-color-gray-3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexShrink: 0,
            }}
          >
            {visibleRightPanel === "rubric" ? (
              <Text fw={600}>Rubric</Text>
            ) : (
              <Group gap={8} align="center">
                <BalooAvatar size={22} />
                <Text fw={600}>{TUTOR_NAME}</Text>
              </Group>
            )}
            <ActionIcon onClick={() => setRightPanel(null)} size="sm" variant="subtle">
              <IconX size={16} />
            </ActionIcon>
          </Box>
          <Box style={{ padding: 16, flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <Box
              style={{
                display: visibleRightPanel === "chat" ? "flex" : "none",
                flex: 1,
                minHeight: 0,
                flexDirection: "column",
              }}
            >
              {aiChatContent}
            </Box>
            <Box
              style={{
                display: visibleRightPanel === "rubric" ? "flex" : "none",
                flex: 1,
                minHeight: 0,
                flexDirection: "column",
              }}
            >
              {rubricContent}
            </Box>
          </Box>
        </Box>
      </Box>

      <ErdGuideModal
        opened={guideOpen}
        onClose={() => setGuideOpen(false)}
        canDismissForever={!guideDismissed}
        onDismissForever={handleDismissGuideForever}
      />

      <input
        ref={fileInputRef}
        type="file"
        accept=".drawio,.xml"
        onChange={handleFileInputChange}
        style={{ display: "none" }}
      />

      <Modal
        opened={exitConfirmOpen}
        onClose={() => setExitConfirmOpen(false)}
        title="Exit focus mode?"
        centered
        withinPortal
        classNames={{ root: BRAND_THEME_CLASS }}
      >
        <Stack gap="md">
          <Text size="sm">
            {/* Positive check for "synced" — not a default — so "idle" and
                "saving" (a write attempted but not yet confirmed) fall on the
                cautious branch rather than being folded into "saved to your
                account" by omission. "storage-full" gets its own branch for
                the same reason: the generic fallback claims the browser has
                it, which is exactly false in that state. */}
            {saveState === "synced"
              ? "You have unsaved changes on the canvas. They are saved to your account and will be restored the next time you open this question, on any device."
              : saveState === "storage-full"
                ? "You have unsaved changes on the canvas. Your browser's storage is full, so they are not saved anywhere right now — not on this device, and not to your account. Download a `.drawio` file before you leave, or free up space and keep drawing to let autosave catch up."
                : "You have unsaved changes on the canvas. They are saved in this browser and will be restored the next time you open this question here, but they have not reached your account, so a different browser or device will not have them. Save a `.drawio` file to keep a copy you can take anywhere."}
          </Text>
          {hasSubmittedAttempt ? null : (
            <Text size="xs" c="dimmed">
              Submitting your diagram is what records your attempt.
            </Text>
          )}
          <Group justify="flex-end" gap="sm">
            <Button variant="subtle" onClick={() => setExitConfirmOpen(false)} disabled={savingBeforeExit}>
              Cancel
            </Button>
            <Button variant="default" onClick={handleConfirmDiscardAndExit} disabled={savingBeforeExit}>
              Discard &amp; exit
            </Button>
            <Button onClick={handleConfirmSaveAndExit} loading={savingBeforeExit}>
              Save &amp; exit
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Box>
  );
},
);
