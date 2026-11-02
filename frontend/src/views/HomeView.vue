<script setup>
import { onMounted, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import MessageBanner from '../components/MessageBanner.vue';
import PageHeading from '../components/PageHeading.vue';
import { api } from '../api.js';
import { formatDate, formatLedgerAmount, formatWon } from '../lib/format.js';
import { session } from '../session.js';

const account = ref(null);
const entries = ref([]);
const loading = ref(true);
const error = ref('');

async function loadHome() {
  loading.value = true;
  error.value = '';
  try {
    const [accountResult, ledger] = await Promise.all([
      api.get('/accounts/me'),
      api.get('/accounts/me/ledger?limit=5&offset=0'),
    ]);
    account.value = accountResult;
    entries.value = ledger.items;
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    loading.value = false;
  }
}

function entryLabel(entryType) {
  const labels = {
    deposit: '입금',
    withdrawal: '출금',
    transfer_in: '받은 송금',
    transfer_out: '보낸 송금',
    loan_disbursement: '대출 실행',
    loan_repayment: '대출 상환',
  };
  return labels[entryType] || '계좌 거래';
}

onMounted(loadHome);
</script>

<template>
  <AppShell title="홈">
    <PageHeading
      :title="`${session.user?.name || ''}님, 안녕하세요`"
      description="계좌와 거래를 한눈에 확인하세요."
    />
    <MessageBanner :message="error" />

    <section v-if="loading" class="loading-card" role="status">
      계좌 정보를 불러오고 있어요.
    </section>
    <template v-else-if="account">
      <section class="balance-card" aria-label="계좌 잔액">
        <div class="balance-card-top">
          <div>
            <p class="card-label">내 입출금 통장</p>
            <p class="account-number">{{ account.account_number }}</p>
          </div>
          <span class="balance-card-mark" aria-hidden="true">포</span>
        </div>
        <p class="balance-caption">사용할 수 있는 잔액</p>
        <p class="balance-value" data-testid="account-balance" :data-amount="account.balance">
          {{ formatWon(account.balance) }}
        </p>
        <div class="balance-actions">
          <RouterLink
            class="button button-light"
            :to="{ name: 'transactions', query: { mode: 'deposit' } }"
          >
            입금
          </RouterLink>
          <RouterLink
            class="button button-light"
            :to="{ name: 'transactions', query: { mode: 'withdrawal' } }"
          >
            출금
          </RouterLink>
          <RouterLink
            class="button button-ghost-light"
            :to="{ name: 'transactions', query: { mode: 'transfer' } }"
          >
            송금
          </RouterLink>
        </div>
      </section>

      <section class="section-block">
        <div class="section-title-row">
          <h2>최근 거래</h2>
          <RouterLink class="text-link" :to="{ name: 'account' }">전체 보기</RouterLink>
        </div>
        <div v-if="entries.length" class="surface-card transaction-list">
          <article v-for="entry in entries" :key="entry.entry_id" class="transaction-row">
            <span
              class="transaction-icon"
              :class="entry.amount < 0 ? 'icon-out' : 'icon-in'"
              aria-hidden="true"
            >
              {{ entry.amount < 0 ? '↗' : '↙' }}
            </span>
            <div class="transaction-copy">
              <strong>{{ entryLabel(entry.entry_type) }}</strong>
              <span>{{ formatDate(entry.posted_at) }}</span>
            </div>
            <strong
              class="transaction-amount"
              :class="entry.amount < 0 ? 'amount-out' : 'amount-in'"
            >
              {{ formatLedgerAmount(entry.amount) }}
            </strong>
          </article>
        </div>
        <div v-else class="surface-card empty-state">
          <span class="empty-icon" aria-hidden="true">⌁</span>
          <strong>아직 거래 내역이 없어요</strong>
          <p>입금하거나 돈을 보내면 여기에 표시돼요.</p>
        </div>
      </section>

      <section class="section-block loan-promo">
        <div>
          <p class="eyebrow">LOAN</p>
          <h2>필요한 대출을 알아보세요</h2>
          <p>상품을 신청하면 은행 직원이 심사해요.</p>
        </div>
        <RouterLink class="button button-outline" :to="{ name: 'loans' }"
          >대출 상품 보기</RouterLink
        >
      </section>
    </template>
    <button
      v-if="error && !loading"
      class="button button-outline button-wide retry-button"
      type="button"
      @click="loadHome"
    >
      다시 불러오기
    </button>
  </AppShell>
</template>
