import { reactive } from 'vue';
import { api, ApiError } from './api.js';

export const session = reactive({
  user: null,
  loaded: false,
  error: null,
});

let loadingSession = null;

export async function loadSession({ force = false } = {}) {
  if (!force && session.loaded) return session.user;
  if (loadingSession) return loadingSession;

  loadingSession = api
    .get('/auth/me')
    .then((user) => {
      session.user = user;
      session.error = null;
      return user;
    })
    .catch((error) => {
      session.user = null;
      session.error = error instanceof ApiError && error.status === 401 ? null : error;
      return null;
    })
    .finally(() => {
      session.loaded = true;
      loadingSession = null;
    });

  return loadingSession;
}

export function clearSession() {
  session.user = null;
  session.loaded = true;
  session.error = null;
}
