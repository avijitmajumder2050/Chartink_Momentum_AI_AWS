export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export const cognitoConfig = {
  domain: import.meta.env.VITE_COGNITO_DOMAIN,
  clientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
  region: import.meta.env.VITE_COGNITO_REGION,
  redirectUri: import.meta.env.VITE_REDIRECT_URI,
  logoutUri: import.meta.env.VITE_LOGOUT_URI,
};
