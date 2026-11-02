<template>
  <main class="public-page callback-page">
    <section class="callback-card">
      <span class="empty-icon" aria-hidden="true">!</span>
      <p class="eyebrow">CONNECTION</p>
      <h1>은행 서버에 연결할 수 없어요</h1>
      <p class="page-description">네트워크를 확인하고 다시 시도해 주세요.</p>
      <RouterLink class="button button-primary button-wide" :to="{ name: 'login' }"
        >로그인 화면으로</RouterLink
      >
    </section>
  </main>
</template>
