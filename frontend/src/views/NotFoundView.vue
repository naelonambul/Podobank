<template>
  <main class="public-page callback-page">
    <section class="callback-card">
      <p class="eyebrow">404</p>
      <h1>페이지를 찾을 수 없어요</h1>
      <RouterLink class="button button-primary button-wide" :to="{ name: 'landing' }"
        >홈으로 돌아가기</RouterLink
      >
    </section>
  </main>
</template>
