<script setup>
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import MessageBanner from '../components/MessageBanner.vue';
import { api } from '../api.js';
import { parseKakaoCallback } from '../lib/kakao.js';
import { loadSession } from '../session.js';

const router = useRouter();
const error = ref('');
const working = ref(true);

onMounted(async () => {
  const callback = parseKakaoCallback(window.location.search);
  if (callback.error) {
    error.value = callback.error;
    working.value = false;
    return;
  }

  try {
    const result = await api.post('/auth/kakao/login', callback);
    if (result.status === 'registration_required') {
      await router.replace({ name: 'signup' });
      return;
    }
    const user = await loadSession({ force: true });
    if (user) await router.replace({ name: 'home' });
    else error.value = '로그인 세션을 확인할 수 없습니다. 다시 시도해 주세요.';
  } catch (requestError) {
    error.value = requestError.message || '카카오 로그인을 완료하지 못했습니다.';
  } finally {
    working.value = false;
  }
});
</script>

<template>
  <main class="public-page callback-page">
    <section class="callback-card" aria-live="polite">
      <span v-if="working" class="loading-spinner" aria-hidden="true"></span>
      <p class="eyebrow">KAKAO LOGIN</p>
      <h1>{{ working ? '로그인 정보를 확인하고 있어요' : '로그인을 완료하지 못했어요' }}</h1>
      <MessageBanner :message="error" />
      <RouterLink v-if="!working" class="button button-primary button-wide" :to="{ name: 'login' }">
        다시 로그인하기
      </RouterLink>
    </section>
  </main>
</template>
