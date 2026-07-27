import type { Configuration, PopupRequest } from '@azure/msal-browser';

/**
 * MSAL (Microsoft Authentication Library) configuration for Microsoft SSO.
 *
 * The "common" authority allows any Microsoft account — work/school (Entra ID)
 * or personal (MSA) — to sign in, mirroring the Azure App registration's tenant
 * setting. The backend validates the resulting ID token, so the frontend only
 * needs to obtain it.
 */
export const msalConfig: Configuration = {
  auth: {
    clientId: process.env.NEXT_PUBLIC_MICROSOFT_CLIENT_ID ?? '',
    authority: `https://login.microsoftonline.com/${process.env.NEXT_PUBLIC_MICROSOFT_TENANT_ID ?? 'common'}`,
    // Popup flow redirects back to the current origin. Register this origin as an
    // SPA redirect URI in the Azure App registration (e.g. http://localhost:3000
    // and the production URL).
    redirectUri: typeof window !== 'undefined' ? window.location.origin : undefined,
  },
  cache: {
    cacheLocation: 'sessionStorage',
  },
};

/**
 * Scopes requested during login. openid + profile + email yield an ID token that
 * carries the user's email claim, which is all the backend needs for whitelist
 * validation.
 */
export const msalLoginRequest: PopupRequest = {
  scopes: ['openid', 'profile', 'email'],
};
