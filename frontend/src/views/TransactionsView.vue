<script setup>
import { onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import MessageBanner from '../components/MessageBanner.vue';
import PageHeading from '../components/PageHeading.vue';
import { api } from '../api.js';
import { formatWon, parsePositiveAmount } from '../lib/format.js';

const route = useRoute();
const router = useRouter();
const modes = [
  { id: 'deposit', label: '입금' },
  { id: 'withdrawal', label: '출금' },
  { id: 'transfer', label: '송금' },
];
const mode = ref(validMode(route.query.mode));
const account = ref(null);
const recipients = ref([]);
const searchQuery = ref('');
const amount = ref('');
const selectedRecipient = ref(null);
const loading = ref(true);
const searching = ref(false);
const submitting = ref(false);
const confirmTransfer = ref(false);
const error = ref('');
const success = ref(null);

function validMode(value) {
  return modes.some((item) => item.id === value) ? value : 'deposit';
}

watch(
  () => route.query.mode,
  (value) => {
    mode.value = validMode(value);
    clearMessages();
  },
);

async function loadTransactionData() {
  loading.value = true;
  error.value = '';
  try {
    const [accountResult, recipientPage] = await Promise.all([
      api.get('/accounts/me'),
      api.get('/accounts/recipients?limit=50&offset=0'),
    ]);
    account.value = accountResult;
    recipients.value = recipientPage.items;
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    loading.value = false;
  }
}

function clearMessages() {
  error.value = '';
  success.value = null;
  confirmTransfer.value = false;
}

async function selectMode(nextMode) {
  clearMessages();
  amount.value = '';
  selectedRecipient.value = null;
  await router.replace({ name: 'transactions', query: { mode: nextMode } });
}

async function searchRecipients() {
  clearMessages();
  const query = searchQuery.value.trim().replace(/\D/g, '');
  if (query.length < 10) {
    error.value = '계좌번호나 휴대전화번호를 10자리 이상 입력해 주세요.';
    return;
  }

  searching.value = true;
  try {
    const result = await api.post('/accounts/recipients/search', { query });
    recipients.value = result.items;
    selectedRecipient.value = null;
    if (!result.items.length) error.value = '일치하는 받는 분을 찾지 못했습니다.';
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    searching.value = false;
  }
}

function chooseRecipient(recipient) {
  selectedRecipient.value = recipient;
  confirmTransfer.value = false;
  success.value = null;
  error.value = '';
}

async function submitTransaction() {
  error.value = '';
  success.value = null;
  const parsedAmount = parsePositiveAmount(amount.value);
  if (parsedAmount === null) {
    error.value = '1원 이상의 금액을 숫자로 입력해 주세요.';
    return;
  }
  if (mode.value === 'transfer' && !selectedRecipient.value) {
    error.value = '먼저 받는 분을 선택해 주세요.';
    return;
  }
  if (mode.value === 'transfer' && !confirmTransfer.value) {
    confirmTransfer.value = true;
    return;
  }

  submitting.value = true;
  try {
    let result;
    if (mode.value === 'deposit') {
      result = await api.post('/transactions/deposit', { amount: parsedAmount });
    } else if (mode.value === 'withdrawal') {
      result = await api.post('/transactions/withdrawal', { amount: parsedAmount });
    } else {
      result = await api.post('/transactions/transfer', {
        destination_account_id: selectedRecipient.value.account_id,
        amount: parsedAmount,
      });
    }
    success.value = {
      amount: parsedAmount,
      balance: result.balance,
      transactionId: result.transaction_id,
      mode: mode.value,
      recipient: selectedRecipient.value?.name,
    };
    amount.value = '';
    confirmTransfer.value = false;
    account.value = await api.get('/accounts/me');
  } catch (requestError) {
    error.value = requestError.message;
    confirmTransfer.value = false;
    if (requestError.status === 401) await router.replace({ name: 'login' });
  } finally {
    submitting.value = false;
  }
}

onMounted(loadTransactionData);
</script>

<template>
  <AppShell title="거래">
    <PageHeading title="입출금·송금" description="계좌에서 처리할 거래를 선택하세요." />
    <MessageBanner :message="error" />
    <MessageBanner
      v-if="success"
      :message="
        success.mode === 'transfer'
          ? `${success.recipient}님에게 ${formatWon(success.amount)}을 보냈어요.`
          : `${formatWon(success.amount)} 거래가 완료됐어요.`
      "
      kind="success"
    />

    <section v-if="loading" class="loading-card" role="status">
      계좌 정보를 불러오고 있어요.
    </section>
    <template v-else-if="account">
      <section class="account-strip surface-card">
        <div>
          <span class="muted-label">내 입출금 통장</span
          ><strong>{{ account.account_number }}</strong>
        </div>
        <strong>{{ formatWon(account.balance) }}</strong>
      </section>

      <div class="segmented-control" role="tablist" aria-label="거래 유형">
        <button
          v-for="item in modes"
          :key="item.id"
          class="segment-button"
          :class="{ selected: mode === item.id }"
          type="button"
          role="tab"
          :aria-selected="mode === item.id"
          @click="selectMode(item.id)"
        >
          {{ item.label }}
        </button>
      </div>

      <section class="surface-card transaction-form-card">
        <template v-if="mode === 'transfer'">
          <div class="form-section-heading">
            <span class="step-number">1</span>
            <div>
              <h2>받는 분</h2>
              <p>계좌번호 또는 휴대전화번호로 찾아요.</p>
            </div>
          </div>
          <form class="recipient-search" @submit.prevent="searchRecipients">
            <label class="field-label" for="recipient-query"
              >받는 분 계좌번호 또는 휴대전화번호</label
            >
            <div class="inline-input-row">
              <input
                id="recipient-query"
                v-model="searchQuery"
                class="text-input"
                type="text"
                inputmode="numeric"
                autocomplete="off"
                placeholder="숫자 10자리 이상"
              />
              <button class="button button-outline" type="submit" :disabled="searching">
                {{ searching ? '찾는 중' : '찾기' }}
              </button>
            </div>
          </form>
          <div v-if="recipients.length" class="recipient-list" aria-label="받는 분 목록">
            <button
              v-for="recipient in recipients"
              :key="recipient.account_id"
              class="recipient-option"
              :class="{ chosen: selectedRecipient?.account_id === recipient.account_id }"
              type="button"
              :aria-pressed="selectedRecipient?.account_id === recipient.account_id"
              @click="chooseRecipient(recipient)"
            >
              <span class="recipient-avatar" aria-hidden="true">{{
                recipient.name.slice(0, 1)
              }}</span>
              <span class="recipient-detail"
                ><strong>{{ recipient.name }}</strong
                ><small
                  >{{ recipient.masked_account_number }} · {{ recipient.phone_suffix }}</small
                ></span
              >
              <span class="recipient-check" aria-hidden="true">{{
                selectedRecipient?.account_id === recipient.account_id ? '✓' : '›'
              }}</span>
            </button>
          </div>
          <p v-else class="inline-empty">
            받는 분 목록을 불러오지 못했거나 등록된 계좌가 없습니다.
          </p>

          <div class="form-divider"></div>
          <div class="form-section-heading">
            <span class="step-number">2</span>
            <div>
              <h2>보낼 금액</h2>
              <p>현재 잔액 {{ formatWon(account.balance) }}</p>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="form-section-heading">
            <span class="step-number">{{ mode === 'deposit' ? '↓' : '↑' }}</span>
            <div>
              <h2>{{ mode === 'deposit' ? '입금할 금액' : '출금할 금액' }}</h2>
              <p>현재 잔액 {{ formatWon(account.balance) }}</p>
            </div>
          </div>
        </template>

        <form class="form-stack amount-form" @submit.prevent="submitTransaction">
          <label class="field-label" for="transaction-amount">금액 (원)</label>
          <div class="amount-input-wrap">
            <input
              id="transaction-amount"
              v-model="amount"
              class="text-input amount-input"
              type="text"
              inputmode="numeric"
              autocomplete="off"
              placeholder="0"
              :aria-describedby="mode === 'transfer' ? 'transfer-note' : 'transaction-note'"
              required
            />
            <span aria-hidden="true">원</span>
          </div>
          <p v-if="mode === 'transfer' && selectedRecipient" class="selected-recipient-note">
            <strong>{{ selectedRecipient.name }}</strong
            >님에게 송금합니다.
          </p>
          <p
            v-if="mode === 'transfer' && confirmTransfer"
            id="transfer-note"
            class="confirm-note"
            role="status"
          >
            {{ selectedRecipient?.name }}님에게 {{ formatWon(parsePositiveAmount(amount) || 0) }}을
            보냅니다. 금액과 받는 분을 확인해 주세요.
          </p>
          <p v-else id="transaction-note" class="form-hint">
            {{
              mode === 'deposit'
                ? '데모 계좌에 입금 처리합니다.'
                : '출금 후 잔액은 음수가 될 수 없습니다.'
            }}
          </p>
          <button class="button button-primary button-wide" type="submit" :disabled="submitting">
            {{
              submitting
                ? '처리 중'
                : mode === 'deposit'
                  ? '입금하기'
                  : mode === 'withdrawal'
                    ? '출금하기'
                    : confirmTransfer
                      ? '확인하고 송금하기'
                      : '송금 금액 확인'
            }}
          </button>
          <p v-if="mode === 'transfer'" class="form-footnote">
            송금 요청 결과가 불확실하면 거래내역을 먼저 확인해 주세요.
          </p>
        </form>
      </section>

      <section v-if="success" class="surface-card transaction-complete">
        <span class="success-mark" aria-hidden="true">✓</span>
        <div>
          <strong>거래가 완료됐어요</strong>
          <p>
            거래번호 {{ success.transactionId }} · 거래 후 잔액 {{ formatWon(success.balance) }}
          </p>
        </div>
        <RouterLink class="text-link" :to="{ name: 'account' }">거래내역</RouterLink>
      </section>
    </template>
  </AppShell>
</template>
