import axios, { AxiosError } from 'axios';
import { API_BASE_URL, API_ENDPOINTS } from '@/config/api.config';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// SSO login calls return 401 to report "invalid/expired token from the provider" —
// that is a login failure, not an expired session, so it must surface as a normal
// rejected promise for the caller to display, not trigger the logout redirect below.
const SSO_LOGIN_PATHS = [API_ENDPOINTS.AUTH.GOOGLE, API_ENDPOINTS.AUTH.MICROSOFT];

// A successful call to any of these must NOT itself count as platform activity —
// the heartbeat would recurse, and the SSO/streak calls aren't meaningful actions.
const NON_ACTIVITY_PATHS = [
  API_ENDPOINTS.LOGIN_ACTIVITY.HEARTBEAT,
  API_ENDPOINTS.AUTH.GOOGLE,
  API_ENDPOINTS.AUTH.MICROSOFT,
];

api.interceptors.request.use(
  (config) => {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => {
    // Any successful authenticated call is a meaningful action — advance the
    // student's session (throttled, best-effort). Skip heartbeat/SSO calls so
    // the ping doesn't recurse or fire on login itself. Imported lazily to avoid
    // a static import cycle with loginActivity.service (which imports this file).
    const url = response.config?.url ?? '';
    if (!NON_ACTIVITY_PATHS.some((path) => url.includes(path))) {
      void import('./loginActivity.service').then((m) => m.loginActivityService.recordActivity());
    }
    return response;
  },
  (error: AxiosError) => {
    const isSsoLoginCall = SSO_LOGIN_PATHS.some((path) => error.config?.url?.includes(path));
    if (error.response?.status === 401 && !isSsoLoginCall) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('access_token');
        window.location.href = '/login';
      }
    }
    // The assessment was ended (by staff Stop, timer expiry, or already submitted): the student's
    // session is finalized server-side. These detail strings only come from assessment endpoints,
    // so route the student back to their list instead of stranding them on a dead question page.
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
    if (detail === 'Assessment has ended.' || detail === 'No active session to submit') {
      if (typeof window !== 'undefined') {
        window.location.href = '/student/assessments';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
