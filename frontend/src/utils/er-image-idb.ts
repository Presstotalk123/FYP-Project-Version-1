/**
 * IndexedDB cache for a student's autosaved ER *image* answer.
 *
 * This is the image-appropriate replacement for the XML draft's localStorage
 * tier (see use-er-draft.ts): localStorage can't hold a multi-MB image —
 * strings only, ~5 MB origin quota, and synchronous writes that would jank the
 * UI. IndexedDB stores the File/Blob natively (no base64 bloat), has a far
 * larger quota, and is async.
 *
 * It is only a CACHE. The server draft is the source of truth (cross-device,
 * gradable at finalize); this exists so returning to a question restores the
 * preview instantly with no download. Every function is best-effort: a browser
 * with IndexedDB disabled, a private-mode quota of zero, or an eviction all
 * resolve to "no cache" rather than throwing, so the hook simply falls back to
 * the server tier.
 */

const DB_NAME = "er-image-drafts";
const DB_VERSION = 1;
const STORE = "images";

/** Same shape/spirit as use-er-draft.ts's draftStorageKey, one entry per
 * (user, question). */
export const imageCacheKey = (userId: number | null, questionId: number): string =>
  `er-image-u${userId ?? "anon"}-bank-${questionId}`;

export type CachedImage = {
  /** The image itself, stored natively. */
  blob: Blob;
  filename: string;
  contentType: string;
  /** When this cache entry was written. */
  savedAt: number;
  /** Server revision this cached copy corresponds to; null if it was written
   * locally (on drop) before the server acknowledged an upload. Used to decide
   * whether the server holds something newer than the cache. */
  syncedRevision: number | null;
};

const idbAvailable = (): boolean =>
  typeof window !== "undefined" && typeof window.indexedDB !== "undefined";

/** Open (and lazily create) the object store. Rejects are swallowed by callers. */
function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!idbAvailable()) {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const request = window.indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
  });
}

/** Promisify one transaction, closing the connection when it settles. */
function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const request = run(tx.objectStore(STORE));
        tx.oncomplete = () => {
          db.close();
          resolve(request.result as T);
        };
        tx.onabort = tx.onerror = () => {
          db.close();
          reject(tx.error ?? new Error("IndexedDB transaction failed"));
        };
      }),
  );
}

export async function putImage(key: string, value: CachedImage): Promise<void> {
  try {
    await withStore("readwrite", (store) => store.put(value, key));
  } catch {
    // Quota/disabled/private-mode — the server tier still holds the image.
  }
}

export async function getImage(key: string): Promise<CachedImage | null> {
  try {
    const value = await withStore<CachedImage | undefined>("readonly", (store) =>
      store.get(key),
    );
    return value ?? null;
  } catch {
    return null;
  }
}

export async function deleteImage(key: string): Promise<void> {
  try {
    await withStore("readwrite", (store) => store.delete(key));
  } catch {
    // Nothing to clean up we can reach; ignore.
  }
}
