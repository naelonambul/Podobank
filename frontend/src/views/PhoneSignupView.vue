<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import MessageBanner from '../components/MessageBanner.vue';
import { api } from '../api.js';
import { loadSession } from '../session.js';

const router = useRouter();
const name = ref('');
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
  if (password.value !== passwordConfirm.value) {
    error.value = '비밀번호가 서로 다릅니다.';
    return;
  }

  submitting.value = true;
  try {
    await api.post('/auth/phone/signup', {
      name: name.value.trim(),
      phone_number: phoneNumber.value,
      password: password.value,
      age: Number(age.value),
      gender: gender.value,
      marital_status: maritalStatus.value,
      is_employed: isEmployed.value,
    });
    const user = await loadSession({ force: true });
    if (!user) throw new Error('가입 정보를 확인하지 못했습니다. 다시 시도해 주세요.');
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
      <RouterLink class="text-link" :to="{ name: 'signup' }">취소</RouterLink>
    </header>

    <section class="auth-card">
      <p class="eyebrow">CREATE ACCOUNT</p>
      <h1>전화번호로 가입하기</h1>
      <p class="page-description">가입을 마치면 입출금 통장이 자동으로 열려요.</p>
      <MessageBanner :message="error" />

      <form class="form-stack" @submit.prevent="completeSignup">
        <label class="field-label" for="phone-signup-name">이름</label>
        <input
          id="phone-signup-name"
          v-model="name"
          class="text-input"
          type="text"
          autocomplete="name"
          maxlength="120"
          required
        />

        <label class="field-label" for="phone-signup-phone">휴대전화번호</label>
        <input
          id="phone-signup-phone"
          v-model="phoneNumber"
          class="text-input"
          type="tel"
          inputmode="numeric"
          autocomplete="tel"
          placeholder="010-0000-0000"
          pattern="[0-9]{3}-[0-9]{4}-[0-9]{4}"
          minlength="13"
          maxlength="13"
          title="숫자 3자리-4자리-4자리 형식으로 입력해 주세요."
          required
        />
        <p class="form-hint">
          SMS 인증은 하지 않아요. 전화번호 소유 여부를 확인하지 않으니 데모용 번호를 입력해 주세요.
        </p>

        <label class="field-label" for="phone-signup-age">나이</label>
        <input
          id="phone-signup-age"
          v-model="age"
          class="text-input"
          type="number"
          inputmode="numeric"
          min="1"
          max="120"
          required
        />

        <label class="field-label" for="phone-signup-gender">성별</label>
        <select id="phone-signup-gender" v-model="gender" class="text-input">
          <option value="female">여성</option>
          <option value="male">남성</option>
        </select>

        <label class="field-label" for="phone-signup-marital">혼인 상태</label>
        <select id="phone-signup-marital" v-model="maritalStatus" class="text-input">
          <option value="single">미혼</option>
          <option value="married">기혼</option>
        </select>

        <label class="check-field">
          <input v-model="isEmployed" type="checkbox" />
          <span>현재 직장이 있어요</span>
        </label>

        <label class="field-label" for="phone-signup-password">비밀번호</label>
        <input
          id="phone-signup-password"
          v-model="password"
          class="text-input"
          type="password"
          autocomplete="new-password"
          minlength="8"
          maxlength="128"
          placeholder="8자 이상 입력해 주세요"
          required
        />

        <label class="field-label" for="phone-signup-password-confirm">비밀번호 확인</label>
        <input
          id="phone-signup-password-confirm"
          v-model="passwordConfirm"
          class="text-input"
          type="password"
          autocomplete="new-password"
          minlength="8"
          maxlength="128"
          required
        />

        <button class="button button-primary button-wide" type="submit" :disabled="submitting">
          {{ submitting ? '가입 중' : '가입하고 계좌 만들기' }}
        </button>
      </form>
    </section>
  </main>
</template>
