import { useCallback, useEffect, useRef, useState } from "react";
import { erDiagramService } from "@/services/er-diagram.service";
import { API_BASE_URL, API_ENDPOINTS } from "@/config/api.config";

/**
 * Tunables, deliberately plain constants rather than build-time env vars.
 *
 * They were briefly `NEXT_PUBLIC_*` overrides, which was a false affordance:
 * a Next.js static export bakes those in at BUILD time, so "configuring" them
 * needs a pipeline change and a redeploy — not something an operator can turn.
 * Worse, `MAX_XML_CHARS` must match the backend's `ER_MAX_XML_CHARS`, which IS
 * settable at runtime; a half-turnable pair invites exactly the drift where the
 * server accepts a payload the client refuses as "too large".
 *
 * So: changing any of these is a code edit, reviewed like any other. If you
 * raise the cap, raise `ER_MAX_XML_CHARS` in backend/app/config.py in the same
 * change — the two are one decision, and keeping them both in code is what
 * makes that obvious.
 *
 * The timings additionally have test coupling: several Playwright specs only
 * discriminate because their poll windows sit inside `IDLE_MS`, so a deployment
 * that diverged from these values would diverge from what the suite covers.
 */

/** Must equal the backend's ER_MAX_XML_CHARS (config.py). */
const MAX_XML_CHARS = 500_000;
/** Quiet period before a flush. Long enough to absorb a drawing burst. */
const IDLE_MS = 3_000;
/** Ceiling so a student who never pauses still syncs. */
const MAX_WAIT_MS = 20_000;
/** Browser's hard keepalive body cap is 64 KB; stay under it. */
const KEEPALIVE_MAX_BYTES = 60_000;
const RETRY_BACKOFF_MS = [2_000, 6_000, 15_000];

/**
 * 4xx other than 401 mean the request itself is wrong — most often the
 * XML-cap mismatch `config.py`'s own comment anticipates (client and server
 * caps can drift) — not that the network hiccuped, so retrying just re-sends
 * the same rejected bytes. 408 (timeout) and 429 (rate limited) are the
 * exceptions: both describe a transient condition despite being in the 4xx
 * range, so they stay on the ladder like a 5xx or a response-less network
 * failure.
 */
const isRetryableStatus = (status: number | undefined): boolean => {
  if (status === undefined) return true; // no HTTP response at all
  if (status < 400) return true; // shouldn't happen for a caught error; fail open
  if (status === 408 || status === 429) return true;
  return status >= 500;
};

export type DraftSaveState =
  | "idle"
  | "saving"
  | "synced"
  | "local-only"
  | "too-large"
  | "storage-full";

export type UseErDraft = {
  initialXml: string;
  saveState: DraftSaveState;
  lastSavedAt: number | null;
  recordChange: (xml: string) => void;
  flushNow: () => Promise<void>;
  conflict: { localXml: string; serverXml: string } | null;
  resolve: (choice: "local" | "server") => void;
  /**
   * Re-seeds `initialXml` from the live canvas ref. `DrawioBoard` only lives
   * inside the caller's focus-mode branch, so leaving and re-entering
   * unmounts and remounts it, and a fresh mount paints itself from
   * `initialXml` at that instant — `recordChange` deliberately never updates
   * that state (see its own comment), so without this it would still hold
   * whatever was true when the FIRST mount reconciled. Call this in the same
   * tick as flipping into focus mode, before the remount happens.
   */
  syncInitialXml: () => void;
};

export type StoredDraft = {
  xml: string;
  savedAt: number;
  /** Revision the server returned for the last payload THIS device pushed. */
  syncedRevision: number | null;
  /** Set on every local write, cleared only by a successful PUT. */
  dirty: boolean;
};

export const draftStorageKey = (userId: number | null, questionId: number): string =>
  `er-draft-u${userId ?? "anon"}-bank-${questionId}`;

/** Key used before drafts moved to localStorage; still read once, then retired. */
export const legacyDraftStorageKey = (questionId: number): string =>
  `er-draft-bank-${questionId}`;

const writeLocalDraft = (
  userId: number | null,
  questionId: number,
  record: StoredDraft,
): boolean => {
  if (typeof window === "undefined") return false;
  try {
    window.localStorage.setItem(
      draftStorageKey(userId, questionId),
      JSON.stringify(record),
    );
    return true;
  } catch {
    return false;
  }
};

export const readLocalDraft = (
  userId: number | null,
  questionId: number,
): StoredDraft | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(draftStorageKey(userId, questionId));
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoredDraft>;
      if (typeof parsed?.xml === "string" && parsed.xml.trim()) {
        return {
          xml: parsed.xml,
          savedAt: typeof parsed.savedAt === "number" ? parsed.savedAt : 0,
          syncedRevision:
            typeof parsed.syncedRevision === "number" ? parsed.syncedRevision : null,
          dirty: parsed.dirty !== false,
        };
      }
      return null;
    }
    const legacyKey = legacyDraftStorageKey(questionId);
    const legacy = window.sessionStorage.getItem(legacyKey);
    if (!legacy?.trim()) {
      // Nothing usable, but still retire a blank/whitespace leftover so it
      // can never resurface once a real localStorage record is written and
      // later evicted under quota pressure.
      if (legacy !== null) window.sessionStorage.removeItem(legacyKey);
      return null;
    }
    const promoted: StoredDraft = { xml: legacy, savedAt: 0, syncedRevision: null, dirty: true };
    // Promote into the durable tier BEFORE retiring the legacy key — removing
    // it first and only then failing to persist (e.g. quota) would drop the
    // draft entirely, which is worse than the leak this is closing. Only on
    // a successful write does the legacy copy stop being needed.
    if (writeLocalDraft(userId, questionId, promoted)) {
      window.sessionStorage.removeItem(legacyKey);
    }
    return promoted;
  } catch {
    return null;
  }
};

/**
 * Owns the student's draw.io draft: an instant localStorage write on every
 * canvas change, plus a debounced, coalesced push to the server.
 *
 * Two tiers rather than one because they fail differently. localStorage is
 * synchronous and works offline, so it is what makes re-entering focus mode
 * instant and what survives a crashed browser. The server is what survives a
 * different machine. Neither alone covers both.
 */
export function useErDraft({
  userId,
  questionId,
  onAdoptXml,
}: {
  userId: number | null;
  questionId: number;
  /**
   * Called whenever adopted XML (an automatic server-wins, or a resolved
   * conflict) must reach an already-mounted draw.io canvas. `initialXml`
   * alone is not enough: DrawioBoard only paints the canvas from that prop
   * on the very first `load` message it sends after the embed's `init`
   * handshake — after that, a prop change just updates a ref no host code
   * ever revisits. The caller is expected to route this to the board's
   * imperative `loadXml` handle, which posts a fresh `load` regardless of
   * mount state.
   */
  onAdoptXml?: (xml: string) => void;
}): UseErDraft {
  const [initialXml, setInitialXml] = useState("");
  const [saveState, setSaveState] = useState<DraftSaveState>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  const onAdoptXmlRef = useRef(onAdoptXml);
  useEffect(() => {
    onAdoptXmlRef.current = onAdoptXml;
  }, [onAdoptXml]);

  // The XML the server acknowledged, so an unchanged canvas is never re-sent.
  const syncedXmlRef = useRef<string>("");
  const syncedRevisionRef = useRef<number | null>(null);
  // The revision the server reported on the reconciliation GET, so a later
  // conflict resolution (choosing either copy) knows what lineage it extends.
  const serverRevisionRef = useRef<number | null>(null);
  // Latest canvas state, whether or not it has reached the server.
  const localXmlRef = useRef<string>("");
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ceilingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Backoff sleep for a retry, kept separate from idle/ceiling: those two are
  // "please flush later" scheduling from recordChange, this is "pause before
  // trying the same in-flight chain again" — conflating them let a fresh edit
  // silently cancel a retry that a caller might be awaiting via flushNow().
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef(false);
  // The promise a caller who arrives mid-request awaits, instead of starting
  // a second concurrent one. Cleared together with inFlightRef.
  const inFlightPromiseRef = useRef<Promise<void> | null>(null);
  const retryIndexRef = useRef(0);

  const clearTimers = useCallback(() => {
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    if (ceilingTimerRef.current) clearTimeout(ceilingTimerRef.current);
    idleTimerRef.current = null;
    ceilingTimerRef.current = null;
  }, []);

  const persistLocal = useCallback(
    (xml: string, dirty: boolean) => {
      const savedAt = Date.now();
      const ok = writeLocalDraft(userId, questionId, {
        xml,
        savedAt,
        syncedRevision: syncedRevisionRef.current,
        dirty,
      });
      if (ok) {
        setLastSavedAt(savedAt);
        // A prior write may have failed on quota and flagged storage-full;
        // this one succeeding (space freed, or the browser evicted something
        // else) means the backstop is back. "saving" rather than guessing
        // synced/local-only here — whichever caller actually knows the sync
        // outcome (flush()'s success branch, or recordChange's demotion)
        // sets the definitive state right after this returns.
        setSaveState((current) => (current === "storage-full" ? "saving" : current));
      } else {
        // Silent before this fix: the tier the whole design leans on for
        // crash safety just failed, while the chip could still read "Saved"
        // from a stale timestamp. Surface it so the student knows to export
        // a file rather than trust either tier.
        setSaveState("storage-full");
      }
      return ok;
    },
    [userId, questionId],
  );

  const flush = useCallback(async (): Promise<void> => {
    clearTimers();
    const xml = localXmlRef.current;
    if (!xml.trim()) return;
    // Nothing changed since the server last acknowledged: the cheapest request
    // is the one never sent, and draw.io fires autosave on selection changes
    // that leave the diagram identical.
    if (xml === syncedXmlRef.current) {
      setSaveState("synced");
      return;
    }
    if (xml.length > MAX_XML_CHARS) {
      setSaveState("too-large");
      return;
    }

    if (inFlightRef.current) {
      // Someone else is already pushing. Ride that request instead of
      // starting a second concurrent one — the one-in-flight-per-question
      // guarantee holds either way. Once it settles, re-check: content that
      // landed after it captured its payload (this call's own xml, or a
      // later edit still) may still need a push, so recurse through the ref
      // rather than resolving early — a caller awaiting flushNow() must not
      // see it resolve before ITS content is actually on the server.
      await inFlightPromiseRef.current;
      await flushRef.current?.();
      return;
    }

    inFlightRef.current = true;
    setSaveState("saving");

    // Loop rather than recursion: each pass is one network attempt for
    // whatever is currently the freshest content, so an edit that lands
    // during a retry's backoff wait is picked up on the next pass rather
    // than being dropped or requiring a caller to notice and re-trigger.
    // inFlightRef (and this promise) stay live for the whole loop, so a
    // flush() that arrives mid-retry joins this chain above instead of
    // racing a second request.
    const attempt = (async () => {
      for (;;) {
        const attemptXml = localXmlRef.current;
        try {
          const result = await erDiagramService.saveDraft(questionId, attemptXml);
          syncedXmlRef.current = attemptXml;
          syncedRevisionRef.current = result.revision;
          retryIndexRef.current = 0;
          // Persist relative to the LIVE content, not the payload just sent:
          // an edit that landed mid-request must not be clobbered back to
          // the older, now-superseded xml and marked clean. Only mark clean
          // when nothing has moved on since this request captured its xml.
          const stillCurrent = localXmlRef.current === attemptXml;
          persistLocal(localXmlRef.current, !stillCurrent);
          // Only claim "synced" — what the chip and exit-modal treat as proof
          // the server has this content — when the live canvas still matches
          // what the server just acknowledged. If newer edits landed
          // mid-request, recordChange already re-armed a flush via its own
          // schedule(); "saving" here is accurate and enough on its own.
          setSaveState(stillCurrent ? "synced" : "saving");
          return;
        } catch (err) {
          const statusCode = (err as { response?: { status?: number } }).response?.status;
          if (!isRetryableStatus(statusCode)) {
            // A deterministic client error: retrying just re-uploads the same
            // rejected payload for the rest of the ladder. 400 is most often
            // the XML-cap mismatch, so it gets the honest "too-large" state
            // already shown for the client-side cap; anything else (401
            // expired token, 403, a deleted question's 404, ...) still isn't
            // on the server, so "local-only" is the truthful-enough
            // fallback. Axios' own auth handling deals with a 401's redirect.
            setSaveState(statusCode === 400 ? "too-large" : "local-only");
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
          // Loop again with whatever localXmlRef now holds.
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
  }, [clearTimers, persistLocal, questionId]);

  // See the module-level trap note: `flush` calls itself (via the joiner
  // branch, once the request it was riding settles) to re-check whether
  // anything newer still needs pushing. Routing that self-call through a ref
  // (kept current by the effect below) avoids `flush` depending on itself,
  // which `react-hooks/exhaustive-deps` would otherwise demand.
  const flushRef = useRef<() => Promise<void>>(flush);
  useEffect(() => {
    flushRef.current = flush;
  }, [flush]);

  const schedule = useCallback(() => {
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    idleTimerRef.current = setTimeout(() => void flush(), IDLE_MS);
    if (!ceilingTimerRef.current) {
      // Jittered +/-20%. The idle timer desynchronises naturally (students
      // pause at different moments), but the ceiling does not: a cohort
      // entering an assessment together arms it together and would fire in
      // lockstep every MAX_WAIT_MS, stacking a whole class's writes onto the
      // same instants, on top of already-peaky assessment-start traffic.
      // Spreading them costs nothing and still guarantees a sync within the
      // ceiling.
      const ceiling = MAX_WAIT_MS * (0.8 + Math.random() * 0.4);
      ceilingTimerRef.current = setTimeout(() => void flush(), ceiling);
    }
  }, [flush]);

  const recordChange = useCallback(
    (xml: string) => {
      if (!xml.trim()) return;
      // draw.io fires `autosave` on selection/viewport changes that leave the
      // diagram byte-identical to what's already stored. The flush path has
      // its own guard for this against the server; this is the local-write
      // equivalent, skipping a JSON.stringify plus a synchronous setItem
      // over up to 500 KB for a no-op event.
      if (xml === localXmlRef.current) return;
      // A retry ladder exhausted for OLDER content must not permanently
      // degrade the rest of the session — a genuinely new edit earns a
      // fresh set of attempts, so a transient outage doesn't strand every
      // later autosave at "local-only" after its first failure.
      //
      // But only when no attempt is in flight. Resetting mid-ladder let a
      // student drawing through an outage restart the counter faster than
      // the shortest 2s rung could advance it, so the ladder never
      // exhausted: the amber "saved on this device only" warning never
      // appeared (the chip read "Saving…" indefinitely while nothing
      // saved), and the retry rate rose to ~1 failing request every 2s
      // instead of the designed 1 per 20s — hammering an endpoint already
      // in trouble. Measured at 17 requests in 48s before this guard.
      // Nothing is lost by waiting: the attempt loop re-reads localXmlRef
      // on each pass, so a retry already carries the newest content; only
      // the counter stops restarting.
      if (!inFlightRef.current) {
        retryIndexRef.current = 0;
      }
      localXmlRef.current = xml;
      // A stale "synced" claim is exactly the falsehood the chip and exit
      // modal must not tell: the instant new content diverges from what the
      // server last acknowledged, demote back to "saving" (queued) rather
      // than let a previous success keep reading as current. Any other
      // unsynced state (saving/local-only/too-large/storage-full) is already
      // truthful and is left alone — persistLocal below has the final say if
      // this very write fails.
      setSaveState((current) => (current === "synced" ? "saving" : current));
      persistLocal(xml, true);
      schedule();
    },
    [persistLocal, schedule],
  );

  // See the `syncInitialXml` doc comment on the return type: deliberately NOT
  // called from recordChange, which would re-render the whole (~1000-line)
  // workspace component on every canvas nudge. Cheap here because it only
  // runs once, on the same tick as entering focus mode.
  const syncInitialXml = useCallback(() => {
    setInitialXml(localXmlRef.current);
  }, []);

  const [conflict, setConflict] = useState<{ localXml: string; serverXml: string } | null>(
    null,
  );

  const adopt = useCallback(
    (xml: string, revision: number | null, synced: boolean) => {
      localXmlRef.current = xml;
      syncedRevisionRef.current = revision;
      syncedXmlRef.current = synced ? xml : "";
      setInitialXml(xml);
      persistLocal(xml, !synced);
      // Covers the board-already-initialized case; a no-op (via optional
      // chaining) when it hasn't mounted yet, since `initialXml` handles that.
      onAdoptXmlRef.current?.(xml);
    },
    [persistLocal],
  );

  const resolve = useCallback(
    (choice: "local" | "server") => {
      const pending = conflict;
      setConflict(null);
      if (!pending) return;
      if (choice === "server") {
        adopt(pending.serverXml, serverRevisionRef.current, true);
        return;
      }
      // Keep this device's work and push it up. `syncedRevision` means "the
      // revision the server returned for the last payload THIS device
      // pushed" (see the field's own doc comment) — stamping the server's
      // current revision here would claim a lineage this device never
      // produced. If the flush below fails and the tab closes before it
      // succeeds, that false stamp would fool a later mount's conditional
      // GET into a silent "unchanged" and skip comparing content at all,
      // letting the eventual flush overwrite the other device's work with no
      // conflict ever re-raised. Leaving it null means a mount that never
      // sees this flush succeed asks again instead of trusting a lineage it
      // doesn't have; the flush itself stamps the real revision once it
      // actually earns one.
      adopt(pending.localXml, null, false);
      void flush();
    },
    [adopt, conflict, flush],
  );

  // Reconcile the two copies BY LINEAGE, never by clock: both timestamps are
  // client-generated, so a second machine with a skewed clock could otherwise
  // silently overwrite good work.
  useEffect(() => {
    if (userId === null) return;
    let cancelled = false;

    const local = readLocalDraft(userId, questionId);
    if (local) {
      localXmlRef.current = local.xml;
      syncedRevisionRef.current = local.syncedRevision;
      if (!local.dirty) syncedXmlRef.current = local.xml;
      setInitialXml(local.xml);
      setLastSavedAt(local.savedAt || null);
    }

    const localXmlAtMount = local?.xml ?? "";

    erDiagramService
      .getDraft(questionId, local?.syncedRevision ?? null)
      .then((server) => {
        if (cancelled) return;

        // The student can start drawing while this request is in flight. Work
        // done since mount is unsaved by definition, so the response — which
        // predates it — must never be written straight to the canvas.
        const liveXml = localXmlRef.current;
        const editedSinceMount = liveXml.trim().length > 0 && liveXml !== localXmlAtMount;
        const localXml = liveXml.trim() ? liveXml : localXmlAtMount;
        const localIsDirty = (local?.dirty ?? false) || editedSinceMount;
        const hasLocal = localXml.trim().length > 0;

        if (!server.exists) {
          // Nothing upstream: whatever this device holds is the truth.
          if (hasLocal) schedule();
          return;
        }
        serverRevisionRef.current = server.revision ?? null;

        if (server.unchanged || !server.xml) {
          // The client already has this revision; nothing to load.
          if (localIsDirty) schedule();
          return;
        }
        if (!hasLocal) {
          adopt(server.xml, server.revision ?? null, true);
          return;
        }
        // Same content — the whole question is moot, and this is also what
        // stops pre-upgrade records (no syncedRevision) from prompting.
        if (localXml === server.xml) {
          syncedXmlRef.current = server.xml;
          syncedRevisionRef.current = server.revision ?? null;
          return;
        }
        const localIsCurrentLineage =
          local?.syncedRevision != null && local.syncedRevision === server.revision;
        if (localIsCurrentLineage) {
          if (localIsDirty) schedule();
          return;
        }
        if (!localIsDirty) {
          adopt(server.xml, server.revision ?? null, true);
          return;
        }
        // Another device moved ahead AND this one has unsaved work. Either
        // silent choice destroys a student's diagram, so ask.
        setConflict({ localXml, serverXml: server.xml });
      })
      .catch(() => {
        if (cancelled) return;
        // The server leg is a bonus; a failure leaves the local copy in charge,
        // which is exactly the behaviour that shipped before this feature.
        setSaveState((current) => (current === "idle" ? "local-only" : current));
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, questionId]);

  // There is no airtight tab-close hook, so this listens for two different
  // signals and treats their overlap as a feature rather than something to
  // dedupe. `visibilitychange -> hidden` fires first and drives the normal
  // flush() path — same request, same retry ladder as any other autosave —
  // and it also covers tab switches and minimising, not just closing. On an
  // actual close, though, that plain (non-keepalive) request can be cancelled
  // by the browser mid-flight once the document starts unloading. `pagehide`
  // fires right after and is the one built to survive that: sendBeacon cannot
  // carry the bearer header the API needs, so this is a size- and
  // token-gated `fetch(keepalive: true)` instead (the browser caps a
  // keepalive body at 64 KB, which a real diagram can exceed). Because
  // `syncedXmlRef` only updates once flush() actually resolves, onPageHide
  // almost always still sees the pre-flush XML and fires its own PUT too — so
  // on a real close BOTH requests typically go out. That is intentional:
  // skipping the keepalive whenever a flush happens to be in flight would
  // remove the one request built to survive teardown at exactly the moment
  // it matters. The cost is one extra revision bump, which is harmless — the
  // backend upsert is idempotent. Past both of these, the localStorage copy
  // is the backstop: the student never loses work on the machine they were
  // sitting at.
  useEffect(() => {
    if (typeof window === "undefined") return;

    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") void flush();
    };

    const onPageHide = () => {
      const xml = localXmlRef.current;
      if (!xml.trim() || xml === syncedXmlRef.current) return;
      const token = window.localStorage.getItem("access_token");
      if (!token) return;
      const body = JSON.stringify({ question_id: questionId, xml });
      // Measure the serialized body, not the raw xml: JSON-escapes every `"`
      // and `\`, and draw.io XML is quote-dense, so the real request is
      // always at least as big as the raw string — near the boundary, big
      // enough to matter.
      if (new Blob([body]).size > KEEPALIVE_MAX_BYTES) return;
      void fetch(`${API_BASE_URL}${API_ENDPOINTS.ER_DIAGRAM.DRAFT}`, {
        method: "PUT",
        keepalive: true,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body,
      }).catch(() => {
        // Nothing useful to do while the page is being torn down.
      });
    };

    // A retry ladder that has exhausted while the tab stays open is otherwise
    // terminal until the next edit — a student who finishes drawing during an
    // outage and then just reads for a while never syncs. `online` is the
    // browser telling us connectivity is plausibly back, so treat it like a
    // fresh edit: reset the ladder and try immediately. flush() itself is a
    // no-op if nothing has changed since the last sync, so firing this
    // unconditionally (there's no cheap way to know in advance whether the
    // last attempt actually failed) costs nothing when there's nothing to
    // push.
    //
    // A bounded periodic re-attempt (poll every N seconds while local-only)
    // was considered and rejected: `online` already covers the realistic
    // recovery case — connectivity actually returning — and any subsequent
    // canvas edit re-arms the ladder anyway. A timer would need its own
    // lifecycle (start on local-only, stop on synced, survive retries) for a
    // gap — staying local-only while genuinely still offline and idle —
    // that isn't harmful: the localStorage tier already has the work, and
    // the chip is honest about it. Not worth the bookkeeping before there's
    // evidence students hit it.
    const onOnline = () => {
      retryIndexRef.current = 0;
      void flush();
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("online", onOnline);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("online", onOnline);
    };
  }, [flush, questionId]);

  useEffect(
    () => () => {
      // Client-side navigation (the "Save and Exit" button, Back, any other
      // router.push) unmounts this hook but keeps the document alive — it
      // fires neither `pagehide` nor `visibilitychange`, so those two exit
      // handlers never run. Without firing a flush here, whatever was still
      // mid-debounce (up to MAX_WAIT_MS of edits) would just be stranded:
      // clearTimers() below cancels the very timers that would have sent it,
      // and nothing else is listening. Doing it at unmount rather than on
      // the button covers every exit path uniformly, not just the one we
      // happen to know about. Reusing flush()'s own guard (skip when idle or
      // already synced) up front avoids firing a request for a no-op
      // unmount.
      //
      // This is fire-and-forget — a cleanup function can't be awaited, and
      // there's nothing left mounted to observe the result — but it still
      // reaches the server: `flush()` runs synchronously up to its first
      // real `await` (inside `erDiagramService.saveDraft`, i.e. axios'
      // `api.put(...)`), so by the time this call returns control here the
      // PUT has already been handed to the network layer. Nothing aborts it
      // from that point on: client-side navigation doesn't tear down the
      // document, and neither this hook nor api.service.ts wires an
      // AbortController to unmount, so the request rides the normal event
      // loop to completion independent of this component's mount state.
      const xml = localXmlRef.current;
      if (xml.trim() && xml !== syncedXmlRef.current) {
        void flush();
      }
      clearTimers();
      // Not routed through clearTimers(): that also runs at the top of every
      // flush(), including the joiner branch, and clearing this there would
      // cancel a live retry sleep without ever resolving its promise —
      // hanging the chain a joiner is awaiting. Unmount used to be the one
      // place a hung promise no longer mattered, but the flush() call above
      // changes that: if a request (or its retry backoff) was already in
      // flight when we got here, that call joined it via
      // inFlightPromiseRef, and the join depends on retryTimerRef's pending
      // timeout actually firing to advance the retry loop. Clearing it
      // unconditionally would cancel the very sleep our join is waiting on,
      // hanging the flush this effect exists to guarantee. So only clear it
      // when nothing is in flight — the original intent (don't let a stray
      // retry keep firing for a question the student has left) still holds
      // for that case, and when something IS in flight the retry ladder is
      // bounded (RETRY_BACKOFF_MS.length attempts) regardless, so leaving it
      // running costs at most a few more seconds in the background.
      if (!inFlightRef.current && retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
      }
    },
    [clearTimers, flush],
  );

  return {
    initialXml,
    saveState,
    lastSavedAt,
    recordChange,
    flushNow: flush,
    conflict,
    resolve,
    syncInitialXml,
  };
}
