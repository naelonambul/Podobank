<script setup>
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '../api.js';
import { clearSession, session } from '../session.js';

defineProps({
  title: { type: String, required: true },
});

const route = useRoute();
const router = useRouter();
const signingOut = ref(false);
const logoutError = ref('');
const isEmployee = computed(() => session.user?.role === 'bank_employee');
const customerLinks = [
  { name: 'home', label: '홈', icon: '⌂' },
  { name: 'account', label: '계좌', icon: '▤' },
  { name: 'transactions', label: '거래', icon: '↔' },
  { name: 'loans', label: '대출', icon: '◉' },
];

async function logout() {
  signingOut.value = true;
  logoutError.value = '';
  try {
    await api.post('/auth/logout');
    clearSession();
    await router.replace({ name: 'landing' });
  } catch {
    logoutError.value = '로그아웃하지 못했습니다. 연결을 확인하고 다시 시도해 주세요.';
  } finally {
    signingOut.value = false;
  }
}
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <RouterLink class="brand" :to="isEmployee ? { name: 'employee-loans' } : { name: 'home' }">
        <span class="brand-mark" aria-hidden="true">포</span>
        <span>포도뱅크</span>
      </RouterLink>
      <div class="header-account">
        <div class="header-user">
          <span class="user-avatar" aria-hidden="true">{{ session.user?.name?.slice(0, 1) }}</span>
          <span class="header-user-name">{{ session.user?.name }}</span>
        </div>
        <RouterLink v-if="!isEmployee" class="header-setting" :to="{ name: 'password-setup' }">
          비밀번호
        </RouterLink>
        <button class="header-logout" type="button" :disabled="signingOut" @click="logout">
          {{ signingOut ? '로그아웃 중' : '로그아웃' }}
        </button>
      </div>
    </header>
    <p v-if="logoutError" class="header-error" role="alert">{{ logoutError }}</p>

    <main class="app-main">
      <div class="page-content">
        <slot />
      </div>
    </main>

    <nav v-if="!isEmployee" class="bottom-nav" aria-label="주 메뉴">
      <RouterLink
        v-for="item in customerLinks"
        :key="item.name"
        class="bottom-nav-link"
        :class="{ active: route.name === item.name }"
        :to="{ name: item.name }"
      >
        <span class="bottom-nav-icon" aria-hidden="true">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
    <nav v-else class="bottom-nav employee-bottom-nav" aria-label="직원 메뉴">
      <RouterLink
        class="bottom-nav-link"
        :class="{ active: route.name === 'employee-loans' }"
        :to="{ name: 'employee-loans' }"
      >
        <span class="bottom-nav-icon" aria-hidden="true">▣</span>
        <span>대출 심사</span>
      </RouterLink>
    </nav>
  </div>
</template>
