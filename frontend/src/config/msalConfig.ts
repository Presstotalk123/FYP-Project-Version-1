import { PublicClientApplication, Configuration, LogLevel } from '@azure/msal-browser';

const msalConfig: Configuration = {
  auth: {
    clientId: process.env.NEXT_PUBLIC_MICROSOFT_CLIENT_ID || '',
    authority: `https://login.microsoftonline.com/${process.env.NEXT_PUBLIC_MICROSOFT_TENANT_ID || 'common'}`,
    redirectUri: typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000',
    postLogoutRedirectUri: typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000',
  },
  cache: {
    cacheLocation: 'sessionStorage',
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
      loggerCallback: (_level, message, containsPii) => {
        if (!containsPii) {
          console.debug('[MSAL]', message);
        }
      },
    },
  },
};

export const loginRequest = {
  scopes: ['openid', 'profile', 'email', 'User.Read'],
};

export const msalInstance = new PublicClientApplication(msalConfig);

// Initialize MSAL and handle popup redirects outside of React to ensure it runs as soon as possible
// and correctly processes the auth token before React hydration can interfere.
if (typeof window !== 'undefined') {
  msalInstance.initialize().then(() => {
    return msalInstance.handleRedirectPromise();
  }).catch((err) => {
    console.error('MSAL initialization/redirect error:', err);
  });
}

export default msalConfig;
