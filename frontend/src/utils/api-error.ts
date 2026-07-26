/** Extract a human-readable message from an axios/API error. */
export const getApiErrorMessage = (err: unknown, fallback = 'Request failed'): string => {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e.response?.data?.detail || e.message || fallback;
};
