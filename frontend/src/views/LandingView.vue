<script setup>
import { useRouter } from 'vue-router';

const router = useRouter();
</script>

<template>
  <main class="public-page landing-page">
    <header class="public-header">
      <RouterLink class="brand" :to="{ name: 'landing' }">
        <span class="brand-mark" aria-hidden="true">포</span>
        <span>포도뱅크</span>
      </RouterLink>
      <RouterLink class="text-link" :to="{ name: 'login' }">로그인</RouterLink>
    </header>

    <section class="landing-card">
      <span class="landing-orbit" aria-hidden="true">●</span>
      <p class="eyebrow">YOUR EVERYDAY BANK</p>
      <h1>돈의 흐름을<br />가볍게 관리해요</h1>
      <p class="landing-copy">
        계좌 확인부터 송금과 대출까지, 필요한 금융 기능을 한곳에서 이용하세요.
      </p>
      <button
        class="button button-primary button-wide"
        type="button"
        @click="router.push({ name: 'login' })"
      >
        포도뱅크 시작하기
      </button>
      <p class="landing-signup">
        처음 방문하셨나요?
        <RouterLink :to="{ name: 'login' }">로그인하고 가입하기</RouterLink>
      </p>
    </section>

    <section class="feature-list" aria-label="포도뱅크 주요 기능">
      <article class="feature-card">
        <span class="feature-icon purple" aria-hidden="true">▤</span>
        <div>
          <h2>계좌와 거래내역</h2>
          <p>잔액과 입출금 내역을 확인해요.</p>
        </div>
      </article>
      <article class="feature-card">
        <span class="feature-icon yellow" aria-hidden="true">↗</span>
        <div>
          <h2>간편한 송금</h2>
          <p>계좌번호나 휴대전화번호로 찾아요.</p>
        </div>
      </article>
      <article class="feature-card">
        <span class="feature-icon green" aria-hidden="true">◉</span>
        <div>
          <h2>대출 관리</h2>
          <p>신청 상태와 상환 일정을 확인해요.</p>
        </div>
      </article>
    </section>
  </main>
</template>
