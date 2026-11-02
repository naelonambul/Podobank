<script setup>
import { ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import MessageBanner from '../components/MessageBanner.vue';
import PageHeading from '../components/PageHeading.vue';
import { api } from '../api.js';

const password = ref('');
const confirmation = ref('');
const submitting = ref(false);
const error = ref('');
const success = ref('');

async function setPassword() {
  error.value = '';
  success.value = '';
  if (password.value !== confirmation.value) {
    error.value = '비밀번호가 서로 다릅니다.';
    return;
  }

  submitting.value = true;
  try {
    await api.post('/auth/password', { password: password.value });
    success.value = '로그인 비밀번호를 설정했어요. 다음부터 휴대전화번호로도 로그인할 수 있습니다.';
    password.value = '';
    confirmation.value = '';
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AppShell title="비밀번호">
    <PageHeading
      title="로그인 비밀번호"
      description="카카오 로그인 고객은 비밀번호를 한 번 설정해 휴대전화번호로도 로그인할 수 있어요."
    />
    <MessageBanner :message="error" />
    <MessageBanner :message="success" kind="success" />
    <section class="surface-card password-card">
      <form class="form-stack" @submit.prevent="setPassword">
        <label class="field-label" for="new-password">새 비밀번호</label>
        <input
          id="new-password"
          v-model="password"
          class="text-input"
          type="password"
          autocomplete="new-password"
          minlength="8"
          maxlength="128"
          placeholder="8자 이상"
          required
        />
        <label class="field-label" for="confirm-password">비밀번호 확인</label>
        <input
          id="confirm-password"
          v-model="confirmation"
          class="text-input"
          type="password"
          autocomplete="new-password"
          minlength="8"
          maxlength="128"
          placeholder="한 번 더 입력해 주세요"
          required
        />
        <button class="button button-primary button-wide" type="submit" :disabled="submitting">
          {{ submitting ? '저장 중' : '비밀번호 설정하기' }}
        </button>
      </form>
      <p class="form-footnote">
        비밀번호는 한 번만 설정할 수 있어요. 이미 설정했다면 이 화면에서 다시 변경할 수 없습니다.
      </p>
    </section>
  </AppShell>
</template>
