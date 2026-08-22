import { useCallback, useEffect, useRef, useState } from "react";
import { erDiagramService } from "@/services/er-diagram.service";
import {
  CachedImage,
  deleteImage,
  getImage,
  imageCacheKey,
  putImage,
} from "@/utils/er-image-idb";

/**
 * Autosave for a student's *uploaded image* ER answer — the image sibling of
 * use-er-draft.ts (which does the same for the draw.io XML). Two tiers:
 *
 *  - IndexedDB, written the instant an image is dropped, so returning to the
 *    question restores the preview with NO network round-trip. It replaces the
 *    XML draft's localStorage tier, which can't hold a multi-MB image.
 *  - A server draft (PUT /er-diagram/image-draft), uploaded immediately on drop.
 *    This is the durable, cross-device, gradable source of truth: the
 *    end-of-assessment finalize sweep grades it even if the student never hit
 *    Submit, and it survives switching items / exiting.
 *
 * Unlike the XML hook there is NO debounce (an image is replaced whole, at most
 * once per visit — there is no continuous-edit stream to coalesce) and NO
 * conflict-resolution UI (a drop replaces wholesale; the server always wins on
 * restore). The on-leave triggers are a GUARD, not a re-save: they re-attempt
 * the upload only when the drop-upload hasn't successfully landed.
 */

export type ImageDraftSaveState =
  | "idle"
  | "saving"
  | "synced"
  | "local-only"
  | "too-large";

const RETRY_BACKOFF_MS = [2_000, 6_000, 15_000];

/** A 413 is the server's size cap; anything else non-network is deterministic.
 * 408/429 and 5xx (and a response-less failure) are worth retrying. */
const isRetryableStatus = (status: number | undefined): boolean => {
  if (status === undefined) return true; // no HTTP response at all
  if (status === 408 || status === 429) return true;
  return status >= 500;
};

export type UseErImageDraft = {
  saveState: ImageDraftSaveState;
  lastSavedAt: number | null;
  /** Called on drop: cache locally + upload immediately. */
  recordImage: (file: File) => void;
  /** Awaitable upload; a no-op when the current image is already synced. For
   * finalize / before-submit / unmount. */
  flushNow: () => Promise<void>;
  /** Student cleared the dropzone: drop the server draft + the local cache. */
  removeImage: () => void;
};

export function useErImageDraft({
  userId,
  questionId,
  onRestore,
}: {
  userId: number | null;
  questionId: number;
  /** Route a restored image (from cache or server) into the workspace so its
   * dropzone preview reappears. */
  onRestore?: (file: File) => void;
}): UseErImageDraft {
  const [saveState, setSaveState] = useState<ImageDraftSaveState>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);

  const onRestoreRef = useRef(onRestore);
  useEffect(() => {
    onRestoreRef.current = onRestore;
  }, [onRestore]);

  // The image the student currently has staged, whether or not it reached the
  // server. Compared by object identity: a fresh drop is always a new File, so
  // identity cleanly distinguishes "new image to save" from "already saved".
  const localFileRef = useRef<File | null>(null);
  // The File the server last acknowledged. localFileRef === syncedFileRef means
  // the current image is already on the server (the on-leave no-op case).
  const syncedFileRef = useRef<File | null>(null);
  const syncedRevisionRef = useRef<number | null>(null);

  const inFlightRef = useRef(false);
  const inFlightPromiseRef = useRef<Promise<void> | null>(null);
  const retryIndexRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cacheKey = imageCacheKey(userId, questionId);

  const writeCache = useCallback(
    (file: File, syncedRevision: number | null) => {
      const savedAt = Date.now();
      const entry: CachedImage = {
        blob: file,
        filename: file.name,
        contentType: file.type || "application/octet-stream",
        savedAt,
        syncedRevision,
      };
      void putImage(cacheKey, entry);
      setLastSavedAt(savedAt);
    },
    [cacheKey],
  );

  const flush = useCallback(async (): Promise<void> => {
    const file = localFileRef.current;
    if (!file) return;
    // Nothing changed since the server acknowledged this exact image: the
    // cheapest upload is the one never sent. This is what makes the on-leave
    // triggers a guard rather than a second upload.
    if (file === syncedFileRef.current) {
      setSaveState("synced");
      return;
    }

    if (inFlightRef.current) {
      // Ride the in-flight upload, then re-check: a newer drop may have landed
      // while it was running, and a caller awaiting flushNow() must not see it
      // resolve before ITS image is on the server.
      await inFlightPromiseRef.current;
      await flushRef.current?.();
      return;
    }

    inFlightRef.current = true;
    setSaveState("saving");

    const attempt = (async () => {
      for (;;) {
        const attemptFile = localFileRef.current;
        if (!attemptFile) return;
        try {
          const result = await erDiagramService.saveImageDraft(questionId, attemptFile);
          syncedFileRef.current = attemptFile;
          syncedRevisionRef.current = result.revision;
          retryIndexRef.current = 0;
          // Re-stamp the cache with the acknowledged revision so a later mount
          // knows this cached copy already matches the server.
          writeCache(attemptFile, result.revision);
          // Only claim "synced" if nothing newer was dropped mid-request.
          setSaveState(localFileRef.current === attemptFile ? "synced" : "saving");
          return;
        } catch (err) {
          const statusCode = (err as { response?: { status?: number } }).response?.status;
          if (statusCode === 413) {
            setSaveState("too-large");
            retryIndexRef.current = RETRY_BACKOFF_MS.length;
            return;
          }
          if (!isRetryableStatus(statusCode)) {
            // 400/401/403/404 — the image is cached locally but not on the
            // server; the next on-leave/flush will try again with fresh state.
            setSaveState("local-only");
            retryIndexRef.current = RETRY_BACKOFF_MS.length;
            return;
          }
          if (retryIndexRef.current >= RETRY_BACKOFF_MS.length) {
            setSaveState("local-only");
            return;
          }
          const delay = RETRY_BACKOFF_MS[retryIndexRef.current];
          retryIndexRef.current += 1;
          setSaveState("saving");
          await new Promise<void>((resolve) => {
            retryTimerRef.current = setTimeout(resolve, delay);
          });
          // Loop with whatever localFileRef now holds.
        }
      }
    })();

    inFlightPromiseRef.current = attempt;
    try {
      await attempt;
    } finally {
      inFlightRef.current = false;
      inFlightPromiseRef.current = null;
    }
  }, [questionId, writeCache]);

  // flush references itself via the joiner branch; route that through a ref so
  // it doesn't depend on itself (matches use-er-draft.ts).
  const flushRef = useRef<() => Promise<void>>(flush);
  useEffect(() => {
    flushRef.current = flush;
  }, [flush]);

  const recordImage = useCallback(
    (file: File) => {
      if (file === localFileRef.current) return;
      localFileRef.current = file;
      // Cache first (instant, survives a crash before the upload lands), then
      // upload immediately — no debounce.
      writeCache(file, null);
      void flush();
    },
    [flush, writeCache],
  );

  const flushNow = useCallback(async (): Promise<void> => {
    await flush();
  }, [flush]);

  const removeImage = useCallback(() => {
    localFileRef.current = null;
    syncedFileRef.current = null;
    syncedRevisionRef.current = null;
    void deleteImage(cacheKey);
    void erDiagramService.deleteImageDraft(questionId).catch(() => {
      // Best-effort: if it fails the draft lingers, but a subsequent replace
      // overwrites it and finalize's unchanged-skip won't re-grade a stale one.
    });
    setSaveState("idle");
    setLastSavedAt(null);
  }, [cacheKey, questionId]);

  // Restore on mount: IndexedDB first (instant, no network), then reconcile with
  // the server and pull the bytes only if the server holds something newer.
  useEffect(() => {
    if (userId === null) return;
    let cancelled = false;

    // The File restored from cache at mount; used to tell whether the student
    // dropped a NEW image before reconciliation finished (don't clobber it).
    let restoredFromCache: File | null = null;

    (async () => {
      const cached = await getImage(cacheKey);
      if (cancelled) return;
      if (cached) {
        const file = new File([cached.blob], cached.filename, {
          type: cached.contentType,
        });
        // Only adopt the cache if the student hasn't already dropped something.
        if (localFileRef.current === null) {
          restoredFromCache = file;
          localFileRef.current = file;
          if (cached.syncedRevision !== null) {
            syncedFileRef.current = file;
            syncedRevisionRef.current = cached.syncedRevision;
            setSaveState("synced");
          }
          setLastSavedAt(cached.savedAt || null);
          onRestoreRef.current?.(file);
        }
      }

      let meta;
      try {
        meta = await erDiagramService.getImageDraftMeta(questionId);
      } catch {
        // Server leg is a bonus; the cache (if any) is already in charge.
        return;
      }
      if (cancelled || !meta.exists) return;

      const cachedRevision = cached?.syncedRevision ?? null;
      const serverIsNewer =
        cachedRevision === null || (meta.revision ?? 0) > cachedRevision;
      // Don't overwrite work the student did since mount: only adopt the server
      // copy if the staged image is still exactly what we restored from cache
      // (or nothing was staged at all).
      const staleLocal =
        localFileRef.current === null || localFileRef.current === restoredFromCache;
      if (!serverIsNewer || !staleLocal) return;

      try {
        const blob = await erDiagramService.getImageDraftContent(questionId);
        if (cancelled) return;
        const file = new File([blob], meta.filename || "er-diagram.png", {
          type: meta.content_type || blob.type || "application/octet-stream",
        });
        if (localFileRef.current !== null && localFileRef.current !== restoredFromCache) {
          return; // student dropped a new image while the content was downloading
        }
        localFileRef.current = file;
        syncedFileRef.current = file;
        syncedRevisionRef.current = meta.revision ?? null;
        writeCache(file, meta.revision ?? null);
        setSaveState("synced");
        onRestoreRef.current?.(file);
      } catch {
        // Content fetch failed — keep whatever the cache gave us.
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, questionId]);

  // Exit/switch guards, mirroring use-er-draft.ts minus the pagehide beacon (a
  // multi-MB image is far over the 64 KB keepalive cap; immediate upload-on-drop
  // makes it moot). Both re-attempt only when the current image isn't yet synced.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") void flush();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [flush]);

  // Unmount flush: covers item-switch / "Save and Exit" client navigation, which
  // fires no visibilitychange. Same SPA context, so an in-flight upload keeps
  // running; this just ensures one is started if the drop-upload hadn't landed.
  useEffect(() => {
    return () => {
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      void flushRef.current?.();
    };
  }, []);

  return { saveState, lastSavedAt, recordImage, flushNow, removeImage };
}
