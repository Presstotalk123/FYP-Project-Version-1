/** Extract a human-readable message from an axios/API error.
 *
 * `detail` is not always a string. FastAPI answers a request that fails schema
 * validation with 422 and an ARRAY of `{type, loc, msg, input}` objects, and
 * returning that verbatim puts an object into React state — which renders as
 * "Objects are not valid as a React child" and takes the page down, hiding the
 * very error it was trying to report.
 */
export const getApiErrorMessage = (err: unknown, fallback = 'Request failed'): string => {
  const e = err as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = e.response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && 'msg' in item) {
          const { msg, loc } = item as { msg?: unknown; loc?: unknown };
          if (typeof msg !== 'string') return null;
          // `loc` names the offending field — "body -> checks -> A1" — which is
          // the difference between "Input should be a valid number" and knowing
          // which check to fix.
          const where = Array.isArray(loc) ? loc.filter((p) => p !== 'body').join('.') : '';
          return where ? `${where}: ${msg}` : msg;
        }
        return null;
      })
      .filter((msg): msg is string => Boolean(msg && msg.trim()));
    if (messages.length > 0) return messages.join('; ');
  }

  if (detail && typeof detail === 'object' && 'msg' in detail) {
    const msg = (detail as { msg?: unknown }).msg;
    if (typeof msg === 'string' && msg.trim()) return msg;
  }

  return e.message || fallback;
};
