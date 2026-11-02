<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import MessageBanner from '../components/MessageBanner.vue';
import { api } from '../api.js';
import { loadSession } from '../session.js';

const router = useRouter();
const phoneNumber = ref('');
const age = ref('');
const gender = ref('female');
const maritalStatus = ref('single');
const isEmployed = ref(true);
const password = ref('');
const passwordConfirm = ref('');
const submitting = ref(false);
const error = ref('');

async function completeSignup() {
  error.value = '';
  if (password.value && password.value !== passwordConfirm.value) {
    error.value = '비밀번호가 서로 다릅니다.';
    return;
  }

  submitting.value = true;
  try {
    const payload = {
      phone_number: phoneNumber.value.replace(/\D/g, ''),
      age: Number(age.value),
      gender: gender.value,
      marital_status: maritalStatus.value,
      is_employed: isEmployed.value,
    };
    if (password.value) payload.password = password.value;
    await api.post('/auth/kakao/signup', payload);
    await loadSession({ force: true });
    await router.replace({ name: 'home' });
  } catch (requestError) {
    error.value = requestError.message || '가입을 완료하지 못했습니다.';
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="public-page auth-page signup-page">
    <header class="public-header">
      <RouterLink class="brand" :to="{ name: 'landing' }">
        <span class="brand-mark" aria-hidden="true">포</span><span>포도뱅크</span>
      </RouterLink>
      <RouterLink class="text-link" :to="{ name: 'login' }">취소</RouterLink>
    </header>

    <section class="auth-card">
      <p class="eyebrow">CREATE ACCOUNT</p>
      <h1>포도뱅크 시작하기</h1>
      <p class="page-description">가입을 마치면 입출금 통장이 자동으로 열려요.</p>
      <MessageBanner :message="error" />

      <form class="form-stack" @submit.prevent="completeSignup">
        <label class="field-label" for="signup-phone">휴대전화번호</label>
        <input
          id="signup-phone"
          v-model="phoneNumber"
          class="text-input"
          type="tel"
          inputmode="numeric"
          autocomplete="tel"
          placeholder="01012345678"
          minlength="10"
          maxlength="15"
          required
        />
        <label class="field-label" for="signup-age">나이</label>
        <input
          id="signup-age"
          v-model="age"
          class="text-input"
          type="number"
          inputmode="numeric"
          min="1"
          max="120"
          required
        />
        <label class="field-label" for="signup-gender">성별</label>
        <select id="signup-gender" v-model="gender" class="text-input">
          <option value="female">여성</option>
          <option value="male">남성</option>
        </select>
        <label class="field-label" for="signup-marital">혼인 상태</label>
        <select id="signup-marital" v-model="maritalStatus" class="text-input">
          <option value="single">미혼</option>
          <option value="married">기혼</option>
        </select>
        <label class="check-field">
          <input v-model="isEmployed" type="checkbox" />
          <span>현재 직장이 있어요</span>
        </label>
        <label class="field-label" for="signup-password">로그인 비밀번호 (선택)</label>
        <input
          id="signup-password"
          v-model="password"
          class="text-input"
          type="password"
          autocomplete="new-password"
          minlength="8"
          maxlength="128"
          placeholder="설정하지 않으면 카카오로만 로그인해요"
        />
        <label v-if="password" class="field-label" for="signup-password-confirm"
          >비밀번호 확인</label
        >
        <input
          v-if="password"
          id="signup-password-confirm"
          v-model="passwordConfirm"
          class="text-input"
          type="password"
          autocomplete="new-password"
          placeholder="비밀번호를 한 번 더 입력해 주세요"
          required
        />
        <button class="button button-primary button-wide" type="submit" :disabled="submitting">
          {{ submitting ? '가입 중' : '가입하고 계좌 만들기' }}
        </button>
      </form>
    </section>
  </main>
</template>
