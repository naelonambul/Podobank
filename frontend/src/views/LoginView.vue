<script setup>
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import MessageBanner from '../components/MessageBanner.vue';
import { api } from '../api.js';
import { loadSession } from '../session.js';

const route = useRoute();
const router = useRouter();
const phoneNumber = ref('');
const password = ref('');
const submitting = ref(false);
const kakaoStarting = ref(false);
const error = ref('');

async function continueWithKakao() {
  kakaoStarting.value = true;
  error.value = '';
  try {
    const result = await api.post('/auth/kakao/state');
    window.location.assign(result.authorization_url);
  } catch (requestError) {
    error.value = requestError.message;
    kakaoStarting.value = false;
  }
}

async function loginLocally() {
  submitting.value = true;
  error.value = '';
  try {
    await api.post('/auth/login', {
      phone_number: phoneNumber.value.replace(/\D/g, ''),
      password: password.value,
    });
    const user = await loadSession({ force: true });
    if (!user) throw new Error('로그인 정보를 확인하지 못했습니다. 다시 로그인해 주세요.');
    if (user.role === 'bank_employee') {
      await router.replace({ name: 'employee-loans' });
    } else {
      const next = route.query.next;
      const isLocalPath =
        typeof next === 'string' && next.startsWith('/') && !next.startsWith('//');
      await router.replace(isLocalPath ? next : { name: 'home' });
    }
  } catch (requestError) {
    error.value = requestError.message || '로그인 정보를 확인해 주세요.';
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="public-page auth-page">
    <header class="public-header">
      <RouterLink class="brand" :to="{ name: 'landing' }">
        <span class="brand-mark" aria-hidden="true">포</span><span>포도뱅크</span>
      </RouterLink>
      <RouterLink class="text-link" :to="{ name: 'landing' }">닫기</RouterLink>
    </header>

    <section class="auth-card">
      <p class="eyebrow">WELCOME BACK</p>
      <h1>다시 만나 반가워요</h1>
      <p class="page-description">로그인하고 내 계좌를 확인하세요.</p>
      <MessageBanner :message="error" />

      <button
        class="button button-kakao button-wide"
        type="button"
        :disabled="kakaoStarting || submitting"
        @click="continueWithKakao"
      >
        <span class="kakao-mark" aria-hidden="true">●</span>
        {{ kakaoStarting ? '카카오 연결 중' : '카카오로 계속하기' }}
      </button>

      <div class="divider"><span>또는 휴대전화로 로그인</span></div>

      <form class="form-stack" @submit.prevent="loginLocally">
        <label class="field-label" for="login-phone">휴대전화번호</label>
        <input
          id="login-phone"
          v-model="phoneNumber"
          class="text-input"
          type="tel"
          inputmode="numeric"
          autocomplete="username"
          placeholder="01012345678"
          required
        />
        <label class="field-label" for="login-password">비밀번호</label>
        <input
          id="login-password"
          v-model="password"
          class="text-input"
          type="password"
          autocomplete="current-password"
          placeholder="비밀번호를 입력해 주세요"
          required
        />
        <button
          class="button button-primary button-wide"
          type="submit"
          :disabled="submitting || kakaoStarting"
        >
          {{ submitting ? '로그인 중' : '로그인' }}
        </button>
      </form>

      <p class="auth-footnote">처음이라면 카카오 로그인을 진행해 가입할 수 있어요.</p>
    </section>
  </main>
</template>
