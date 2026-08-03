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
  IconMessageCircle,
  IconNotebook,
  IconReportAnalytics,
  IconX,
} from "@tabler/icons-react";
import type { ERDiagramWorkspaceQuestion } from "@/components/ERDiagramWorkspace";
import drawioTheme from "@/components/DrawioTheme.module.css";

type DrawioFocusLayoutProps = {
  question: ERDiagramWorkspaceQuestion;
  canvas: ReactNode;
  problemContent: ReactNode;
  aiChatContent: ReactNode;
  rubricContent: ReactNode;
  onSubmit: () => void;
  onSaveToFile: () => void;
  onLoadFromFile: (file: File) => void;
  onExit: () => void;
  submitting: boolean;
  scorePercent: number | null;
  hasSubmittedAttempt: boolean;
  showRubricToggle: boolean;
  isDirty: boolean;
};

type RightPanel = "chat" | "rubric" | null;

/** Which side panel a drag is currently resizing, if any. */
type ResizingSide = "problem" | "right" | null;

export type DrawioFocusLayoutHandle = {
  requestExit: () => void;
};

const TOOLBAR_HEIGHT = 48;
const PILL_WIDTH = 104;

// Panel sizing, shared by the left (Problem) and right (AI Chat / Rubric)
// panels so both resize with identical feel.
const PANEL_MIN_WIDTH = 280;
const PANEL_MAX_FRACTION = 0.6;
// Drag narrower than this and the panel closes, rather than leaving a sliver.
const PANEL_COLLAPSE_WIDTH = 150;

// Scoped brand-purple + Geist override for Mantine (DrawioTheme.module.css).
// Portalled components render outside this tree, so they carry the class too.
const BRAND_THEME_CLASS = drawioTheme.drawioTheme;

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
    },
    ref,
  ) {
  const [problemOpen, setProblemOpen] = useState(false);
  const [problemWidth, setProblemWidth] = useState(400);
  const [rightWidth, setRightWidth] = useState(420);
  const [resizing, setResizing] = useState<ResizingSide>(null);
  const [rightPanel, setRightPanel] = useState<RightPanel>(null);
  const [exitConfirmOpen, setExitConfirmOpen] = useState(false);
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

  useImperativeHandle(ref, () => ({ requestExit: handleExitClick }), [handleExitClick]);

  const handleConfirmSaveAndExit = () => {
    onSaveToFile();
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
            leftSection={<IconMessageCircle size={14} />}
            onClick={() => toggleRightPanel("chat")}
            w={PILL_WIDTH}
          >
            AI Chat
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
            <Text fw={600}>{visibleRightPanel === "rubric" ? "Rubric" : "AI Chat"}</Text>
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
            You have unsaved changes on the canvas. Auto-save keeps a copy in this browser tab,
            but it will be lost when the tab closes. Save a `.drawio` file to keep your work
            outside the browser.
          </Text>
          {hasSubmittedAttempt ? null : (
            <Text size="xs" c="dimmed">
              Submitting your diagram is what records your attempt.
            </Text>
          )}
          <Group justify="flex-end" gap="sm">
            <Button variant="subtle" onClick={() => setExitConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="default" onClick={handleConfirmDiscardAndExit}>
              Discard &amp; exit
            </Button>
            <Button onClick={handleConfirmSaveAndExit}>Save &amp; exit</Button>
          </Group>
        </Stack>
      </Modal>
    </Box>
  );
},
);
