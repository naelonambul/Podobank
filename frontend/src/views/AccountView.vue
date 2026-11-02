<script setup>
import { onMounted, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import MessageBanner from '../components/MessageBanner.vue';
import PageHeading from '../components/PageHeading.vue';
import { api } from '../api.js';
import { formatDate, formatLedgerAmount, formatWon } from '../lib/format.js';

const account = ref(null);
const entries = ref([]);
const loading = ref(true);
const error = ref('');

async function loadAccount() {
  loading.value = true;
  error.value = '';
  try {
    const [accountResult, ledger] = await Promise.all([
      api.get('/accounts/me'),
      api.get('/accounts/me/ledger?limit=50&offset=0'),
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

onMounted(loadAccount);
</script>

<template>
  <AppShell title="계좌">
    <PageHeading title="내 계좌" description="입출금 통장과 거래내역을 확인하세요." />
    <MessageBanner :message="error" />
    <section v-if="loading" class="loading-card" role="status">
      계좌 정보를 불러오고 있어요.
    </section>
    <template v-else-if="account">
      <section class="account-summary surface-card">
        <div class="account-summary-heading">
          <span class="account-type-pill">입출금</span>
          <span class="account-summary-caption">기본 계좌</span>
        </div>
        <p class="account-number">{{ account.account_number }}</p>
        <p class="balance-caption">현재 잔액</p>
        <p class="account-balance" data-testid="account-balance" :data-amount="account.balance">
          {{ formatWon(account.balance) }}
        </p>
        <div class="balance-actions">
          <RouterLink
            class="button button-primary"
            :to="{ name: 'transactions', query: { mode: 'deposit' } }"
          >
            입금
          </RouterLink>
          <RouterLink
            class="button button-outline"
            :to="{ name: 'transactions', query: { mode: 'withdrawal' } }"
          >
            출금
          </RouterLink>
          <RouterLink
            class="button button-outline"
            :to="{ name: 'transactions', query: { mode: 'transfer' } }"
          >
            송금
          </RouterLink>
        </div>
      </section>

      <section class="section-block">
        <div class="section-title-row">
          <h2>거래내역</h2>
          <button
            class="icon-button"
            type="button"
            aria-label="거래내역 새로고침"
            @click="loadAccount"
          >
            ↻
          </button>
        </div>
        <div v-if="entries.length" class="surface-card transaction-list">
          <article
            v-for="entry in entries"
            :key="entry.entry_id"
            class="transaction-row ledger-row"
          >
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
              <small>거래번호 {{ entry.transaction_id }}</small>
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
          <strong>거래내역이 없습니다</strong>
          <p>입금, 출금, 송금 결과가 여기에 표시됩니다.</p>
        </div>
      </section>
    </template>
    <button
      v-if="error && !loading"
      class="button button-outline button-wide retry-button"
      type="button"
      @click="loadAccount"
    >
      다시 불러오기
    </button>
  </AppShell>
</template>
