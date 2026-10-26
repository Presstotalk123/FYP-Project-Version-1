'use client';

import { useEffect, useRef, useSyncExternalStore } from 'react';
import { usePathname } from 'next/navigation';
import { Button, Card, Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconMaximize } from '@tabler/icons-react';
import { useAssessmentProgress } from '@/contexts/AssessmentProgressContext';

const LEFT_WINDOW_NOTIFICATION_ID = 'assessment-left-window';

// Overview and item workspaces only — not the landing/join page, which shares the layout.
const IN_PROGRESS_PATH = /\/student\/assessments\/\d+\/(overview|items\/)/;

// Clicks that open the native file dialog, which takes focus from the page without the
// student leaving. Mantine's Dropzone opens it via showOpenFilePicker, not an input click.
const FILE_PICKER_SELECTOR = 'input[type="file"], .mantine-Dropzone-root';

// Session-scoped like the progress navigator: remembers that this attempt was in
// fullscreen once, so the overlay can tell "exited" (flagged) from "not entered yet".
function fullscreenStorageKey(assessmentId: number): string {
  return `assessment-fullscreen:${assessmentId}`;
}

function loadEnteredFullscreen(assessmentId: number): boolean {
  try {
    return window.sessionStorage.getItem(fullscreenStorageKey(assessmentId)) === '1';
  } catch {
    return false;
  }
}

function saveEnteredFullscreen(assessmentId: number): void {
  try {
    window.sessionStorage.setItem(fullscreenStorageKey(assessmentId), '1');
  } catch {
    // sessionStorage may throw (quota, private mode) — the overlay just shows the softer wording.
  }
}

function subscribeFullscreen(onChange: () => void): () => void {
  document.addEventListener('fullscreenchange', onChange);
  return () => document.removeEventListener('fullscreenchange', onChange);
}

function getIsFullscreen(): boolean {
  return !!document.fullscreenElement;
}

// Without the Fullscreen API (e.g. iPhone Safari) the overlay is skipped, so the
// student is never locked out; tab-switch warnings still apply.
function getFullscreenSupported(): boolean {
  return !!document.fullscreenEnabled;
}

function subscribeNever(): () => void {
  return () => {};
}

export function requestAssessmentFullscreen(): void {
  document.documentElement.requestFullscreen?.().catch(() => {
    // Denied or unsupported — the guard's overlay asks again with its own button.
  });
}

/**
 * Anti-cheat fullscreen and focus enforcement for a student taking an assessment.
 * Mounted once by the assessment layout, so it persists across item navigation.
 *
 * - Outside fullscreen, the page is covered by a blurred overlay with a button to
 *   return to fullscreen; keyboard input to the workspace underneath is blocked.
 * - Switching tabs or leaving the window shows a 20 s warning on return.
 *
 * Nothing is recorded: the "flagged" wording is a deterrent only.
 */
export function AssessmentIntegrityGuard() {
  const { assessmentId, antiCheat, antiCheatLoaded } = useAssessmentProgress();
  const pathname = usePathname();
  const watching = antiCheat && antiCheatLoaded && assessmentId !== null && IN_PROGRESS_PATH.test(pathname ?? '');

  const isFullscreen = useSyncExternalStore(subscribeFullscreen, getIsFullscreen, () => true);
  const fullscreenSupported = useSyncExternalStore(subscribeNever, getFullscreenSupported, () => false);
  const overlayRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (watching && isFullscreen && assessmentId !== null) saveEnteredFullscreen(assessmentId);
  }, [watching, isFullscreen, assessmentId]);

  // Exit fullscreen when the attempt ends (submit / time-up navigate out of the
  // layout) or the student leaves the in-progress pages.
  useEffect(() => {
    if (!watching) return;
    return () => {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    };
  }, [watching]);

  const blocked = watching && fullscreenSupported && !isFullscreen;
  // Read at render: only ever true on the client, after the save effect above has run
  // for any earlier fullscreen period.
  const enteredBefore = blocked && assessmentId !== null && loadEnteredFullscreen(assessmentId);

  // While blocked, move focus out of the editor and swallow keyboard input aimed at
  // anything behind the overlay.
  useEffect(() => {
    if (!blocked) return;
    (document.activeElement as HTMLElement | null)?.blur?.();
    buttonRef.current?.focus();

    const swallow = (e: Event) => {
      if (e.target instanceof Node && overlayRef.current?.contains(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
    };
    const events = ['keydown', 'keypress', 'keyup', 'paste'] as const;
    events.forEach((type) => window.addEventListener(type, swallow, true));
    return () => events.forEach((type) => window.removeEventListener(type, swallow, true));
  }, [blocked]);

  // Tab / window switching. document.hasFocus() rather than bare blur events: it stays
  // true while focus is inside the draw.io iframe, and the poll catches leaving from
  // inside that iframe, where the parent window gets no blur event.
  useEffect(() => {
    if (!watching) return;
    let away = false;
    // Set while the native file dialog is open; cleared when the window regains focus.
    let pickingFile = false;

    const markAwayIfLeft = () => {
      if (pickingFile) return;
      if (document.visibilityState === 'hidden' || !document.hasFocus()) away = true;
    };

    const notifyIfReturned = () => {
      if (!away || document.visibilityState !== 'visible' || !document.hasFocus()) return;
      away = false;
      notifications.hide(LEFT_WINDOW_NOTIFICATION_ID);
      notifications.show({
        id: LEFT_WINDOW_NOTIFICATION_ID,
        color: 'red',
        title: 'Leaving the assessment is not allowed',
        message: 'Switching tabs or leaving the window is not allowed. This activity has been flagged.',
        autoClose: 20000,
      });
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') markAwayIfLeft();
      else notifyIfReturned();
    };
    const onBlur = () => setTimeout(markAwayIfLeft, 0);
    const onFocus = () => {
      if (pickingFile) {
        pickingFile = false;
        away = false;
        return;
      }
      notifyIfReturned();
    };
    const onClick = (e: MouseEvent) => {
      if (e.target instanceof Element && e.target.closest(FILE_PICKER_SELECTOR)) pickingFile = true;
    };
    const poll = setInterval(() => {
      markAwayIfLeft();
      notifyIfReturned();
    }, 1000);

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('blur', onBlur);
    window.addEventListener('focus', onFocus);
    document.addEventListener('click', onClick, true);
    return () => {
      clearInterval(poll);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('click', onClick, true);
    };
  }, [watching]);

  if (!blocked) return null;

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="assessment-fullscreen-title"
      style={{
        position: 'fixed',
        inset: 0,
        // Above Mantine modals (200) and popovers (300), below notifications (400).
        zIndex: 350,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        background: 'rgba(0, 0, 0, 0.45)',
      }}
    >
      <Card shadow="lg" padding="xl" radius="md" withBorder maw={460}>
        <Stack gap="md" align="center" ta="center">
          <Title order={3} id="assessment-fullscreen-title">
            {enteredBefore ? 'Return to fullscreen to resume' : 'Enter fullscreen to continue'}
          </Title>
          <Text>
            {enteredBefore
              ? 'Exiting fullscreen is not allowed during this assessment. This activity has been flagged.'
              : 'This assessment must be taken in fullscreen.'}
          </Text>
          <Button
            ref={buttonRef}
            size="md"
            leftSection={<IconMaximize size={18} />}
            onClick={requestAssessmentFullscreen}
          >
            {enteredBefore ? 'Return to fullscreen' : 'Enter fullscreen'}
          </Button>
        </Stack>
      </Card>
    </div>
  );
}
