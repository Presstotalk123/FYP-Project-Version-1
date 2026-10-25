'use client';

import { useEffect } from 'react';
import { notifications } from '@mantine/notifications';

/**
 * Blocks pasting (and drag-dropping) content that was copied from outside the page
 * while `enabled`, e.g. a query copied from another website or a notes file. Text
 * copied on the page itself — the question description, the student's own editor —
 * can still be pasted.
 *
 * The browser doesn't say where clipboard content came from, so every copy/cut on
 * the page is recorded and a paste is only let through when its text matches one of
 * those recordings. The record is module-level, so copying in one assessment item and
 * pasting in the next (SPA navigation) still works; copies made in another tab — even
 * of this site — count as external.
 *
 * The paste listener runs in the capture phase on `window`, ahead of Monaco's own
 * textarea handler, so a blocked paste never reaches the editor. Monaco's right-click
 * "Paste" reads `navigator.clipboard` directly and bypasses the paste event, so the
 * editor panels also disable Monaco's context menu during assessments.
 *
 * This is a client-side deterrent only — it can't stop someone using devtools.
 */

const MAX_RECORDED_COPIES = 20;
const internalCopies: string[] = [];

const normalize = (text: string) => text.replace(/\r\n?/g, '\n').trim();

function recordCopy(text: string) {
  const normalized = normalize(text);
  if (!normalized) return;
  const existing = internalCopies.indexOf(normalized);
  if (existing !== -1) internalCopies.splice(existing, 1);
  internalCopies.push(normalized);
  if (internalCopies.length > MAX_RECORDED_COPIES) internalCopies.shift();
}

function copiedText(event: ClipboardEvent): string {
  // Monaco (and anything else that overrides copy) writes the text via setData.
  const fromClipboard = event.clipboardData?.getData('text/plain');
  if (fromClipboard) return fromClipboard;

  const active = document.activeElement;
  if (active instanceof HTMLTextAreaElement || active instanceof HTMLInputElement) {
    const { selectionStart, selectionEnd, value } = active;
    if (selectionStart != null && selectionEnd != null && selectionEnd > selectionStart) {
      return value.slice(selectionStart, selectionEnd);
    }
  }
  return window.getSelection()?.toString() ?? '';
}

function isInternal(data: DataTransfer | null): boolean {
  if (!data) return true;
  if (data.files.length > 0) return false;
  const text = normalize(data.getData('text/plain'));
  if (!text) return true;
  return internalCopies.includes(text);
}

function notifyBlocked() {
  notifications.show({
    id: 'external-paste-blocked',
    color: 'red',
    title: 'Paste blocked',
    message: 'Pasting content from outside the assessment is disabled.',
  });
}

export function useBlockExternalPaste(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;

    const handleCopy = (event: ClipboardEvent) => recordCopy(copiedText(event));
    // Dragging selected text from elsewhere on the page counts as an internal copy.
    const handleDragStart = () => recordCopy(window.getSelection()?.toString() ?? '');

    const handlePaste = (event: ClipboardEvent) => {
      if (isInternal(event.clipboardData)) return;
      event.preventDefault();
      event.stopPropagation();
      notifyBlocked();
    };

    const handleDrop = (event: DragEvent) => {
      if (isInternal(event.dataTransfer)) return;
      event.preventDefault();
      event.stopPropagation();
      notifyBlocked();
    };

    window.addEventListener('copy', handleCopy);
    window.addEventListener('cut', handleCopy);
    window.addEventListener('dragstart', handleDragStart);
    window.addEventListener('paste', handlePaste, true);
    window.addEventListener('drop', handleDrop, true);
    return () => {
      window.removeEventListener('copy', handleCopy);
      window.removeEventListener('cut', handleCopy);
      window.removeEventListener('dragstart', handleDragStart);
      window.removeEventListener('paste', handlePaste, true);
      window.removeEventListener('drop', handleDrop, true);
    };
  }, [enabled]);
}
