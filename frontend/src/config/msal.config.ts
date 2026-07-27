import type { Configuration, RedirectRequest } from '@azure/msal-browser';

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
    // Redirect flow sends the user back to the current origin. Register this
    // origin as an SPA redirect URI in the Azure App registration (e.g.
    // http://localhost:3000 and the production URL).
    redirectUri: typeof window !== 'undefined' ? window.location.origin : undefined,
  },
  cache: {
    cacheLocation: 'sessionStorage',
  },
};

/**
 * Login request used with loginRedirect.
 *
 * scopes: openid + profile + email yield an ID token that carries the user's
 * email claim, which is all the backend needs for whitelist validation.
 *
 * prompt: 'select_account' forces Microsoft's account picker every time, rather
 * than silently reusing whatever Microsoft account session is already cached in
 * the browser. Without this, a returning user (or one signed into multiple
 * Microsoft accounts) has no way to choose a different account — Microsoft just
 * completes SSO instantly with whichever session it already has.
 */
export const msalLoginRequest: RedirectRequest = {
  scopes: ['openid', 'profile', 'email'],
  prompt: 'select_account',
};
