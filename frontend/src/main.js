import { createApp } from 'vue';
import App from './App.vue';
import { setUnauthorizedHandler } from './api.js';
import router from './router.js';
import { clearSession, session } from './session.js';
import './style.css';

setUnauthorizedHandler(async () => {
  const wasAuthenticated = Boolean(session.user);
  const next = router.currentRoute.value.fullPath;
  clearSession();
  if (wasAuthenticated && router.currentRoute.value.name !== 'login') {
    await router.replace({ name: 'login', query: { next } });
  }
});

createApp(App).use(router).mount('#app');
