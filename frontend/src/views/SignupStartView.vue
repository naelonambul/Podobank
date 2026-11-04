<script setup>
import { ref } from 'vue';
import MessageBanner from '../components/MessageBanner.vue';
import { api } from '../api.js';

const starting = ref(false);
const error = ref('');

async function startSignupWithKakao() {
  starting.value = true;
  error.value = '';
  try {
    const result = await api.post('/auth/kakao/state');
    window.location.assign(result.authorization_url);
  } catch (requestError) {
    error.value = requestError.message || '카카오 가입을 시작하지 못했습니다.';
    starting.value = false;
  }
}
</script>

<template>
  <main class="public-page auth-page signup-page">
    <header class="public-header">
      <RouterLink class="brand" :to="{ name: 'landing' }">
        <span class="brand-mark" aria-hidden="true">포</span><span>포도뱅크</span>
      </RouterLink>
      <RouterLink class="text-link" :to="{ name: 'landing' }">닫기</RouterLink>
    </header>

    <section class="auth-card">
      <p class="eyebrow">CREATE ACCOUNT</p>
      <h1>포도뱅크 회원가입</h1>
      <p class="page-description">전화번호 또는 카카오 계정으로 가입할 수 있어요.</p>
      <MessageBanner :message="error" />

      <RouterLink class="button button-primary button-wide" :to="{ name: 'phone-signup' }">
        전화번호로 가입하기
      </RouterLink>

      <button
        class="button button-kakao button-wide"
        type="button"
        :disabled="starting"
        @click="startSignupWithKakao"
      >
        <span class="kakao-mark" aria-hidden="true">●</span>
        {{ starting ? '카카오 연결 중' : '카카오로 가입하기' }}
      </button>

      <p class="auth-footnote">
        이미 계정이 있으신가요?
        <RouterLink :to="{ name: 'login' }">로그인</RouterLink>
      </p>
    </section>
  </main>
</template>
