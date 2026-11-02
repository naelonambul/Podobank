<script setup>
import { computed, onMounted, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import MessageBanner from '../components/MessageBanner.vue';
import PageHeading from '../components/PageHeading.vue';
import { api } from '../api.js';
import { formatDate, formatWon, parsePositiveAmount } from '../lib/format.js';

const products = ref([]);
const applications = ref([]);
const selectedProductId = ref(null);
const repaymentAmount = ref('');
const loading = ref(true);
const submitting = ref(false);
const error = ref('');
const success = ref('');
const activeApplication = computed(
  () =>
    applications.value.find((item) => item.status === 'pending' || item.status === 'repaying') ||
    null,
);
const selectedProduct = computed(
  () => products.value.find((item) => item.id === selectedProductId.value) || null,
);

function remainingPrincipal(application) {
  const paid = application.repayments
    .filter((repayment) => repayment.status === 'paid')
    .reduce((total, repayment) => total + repayment.amount, 0);
  return Math.max(0, application.principal_amount - paid);
}

function overdueCount(application) {
  return application.repayments.filter((repayment) => repayment.status === 'overdue').length;
}

function statusLabel(status) {
  const labels = {
    pending: '직원 심사 중',
    repaying: '상환 중',
    rejected: '거절',
    repaid: '상환 완료',
  };
  return labels[status] || status;
}

function repaymentStatusLabel(status) {
  const labels = { scheduled: '예정', paid: '납부 완료', overdue: '연체' };
  return labels[status] || status;
}

async function loadLoans() {
  loading.value = true;
  error.value = '';
  try {
    const [productResponse, applicationResponse] = await Promise.all([
      api.get('/loans/products'),
      api.get('/loans/me'),
    ]);
    products.value = productResponse.items;
    applications.value = applicationResponse.items;
    if (!selectedProductId.value && products.value.length)
      selectedProductId.value = products.value[0].id;
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    loading.value = false;
  }
}

async function applyForLoan() {
  if (!selectedProduct.value || activeApplication.value) return;
  submitting.value = true;
  error.value = '';
  success.value = '';
  try {
    await api.post('/loans/applications', { product_id: selectedProduct.value.id });
    success.value = '대출 신청을 접수했어요. 은행 직원의 심사를 기다려 주세요.';
    await loadLoans();
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    submitting.value = false;
  }
}

async function repayOverdue(application) {
  const amount = parsePositiveAmount(repaymentAmount.value);
  if (amount === null) {
    error.value = '1원 이상의 금액을 입력해 주세요.';
    return;
  }
  if (amount % application.monthly_installment !== 0) {
    error.value = `월 상환액 ${formatWon(application.monthly_installment)}의 정수배로 입력해 주세요.`;
    return;
  }

  submitting.value = true;
  error.value = '';
  success.value = '';
  try {
    await api.post(`/loans/me/${application.id}/repayments`, { amount });
    repaymentAmount.value = '';
    success.value = '연체 회차를 납부했어요.';
    await loadLoans();
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    submitting.value = false;
  }
}

onMounted(loadLoans);
</script>

<template>
  <AppShell title="대출">
    <PageHeading title="대출" description="등록된 상품을 신청하고 상환 일정을 확인하세요." />
    <MessageBanner :message="error" />
    <MessageBanner :message="success" kind="success" />
    <section v-if="loading" class="loading-card" role="status">
      대출 정보를 불러오고 있어요.
    </section>

    <template v-else>
      <section v-if="activeApplication" class="section-block">
        <div class="section-title-row">
          <h2>내 대출</h2>
          <span class="status-pill" :class="`status-${activeApplication.status}`">{{
            statusLabel(activeApplication.status)
          }}</span>
        </div>
        <article class="surface-card loan-summary-card">
          <div class="loan-summary-top">
            <div>
              <p class="muted-label">{{ activeApplication.product_name }}</p>
              <strong class="loan-remaining">{{
                formatWon(remainingPrincipal(activeApplication))
              }}</strong
              ><span class="muted-label">남은 원금</span>
            </div>
            <span class="loan-mark" aria-hidden="true">◉</span>
          </div>
          <div class="loan-detail-grid">
            <div>
              <span>신청 금액</span
              ><strong>{{ formatWon(activeApplication.principal_amount) }}</strong>
            </div>
            <div>
              <span>상환 기간</span><strong>{{ activeApplication.term_months }}개월</strong>
            </div>
            <div>
              <span>월 상환액</span
              ><strong>{{ formatWon(activeApplication.monthly_installment) }}</strong>
            </div>
            <div>
              <span>신청일</span><strong>{{ formatDate(activeApplication.created_at) }}</strong>
            </div>
          </div>
          <p v-if="activeApplication.status === 'pending'" class="loan-note">
            승인 전에는 대출금이 입금되지 않아요.
          </p>
          <p v-else class="loan-note">
            승인된 대출은 매월 1일 자동 상환돼요. 잔액이 부족한 회차는 연체로 표시됩니다.
          </p>
        </article>

        <div v-if="activeApplication.status === 'repaying'" class="repayment-list surface-card">
          <h3>상환 일정</h3>
          <article
            v-for="repayment in activeApplication.repayments"
            :key="repayment.id"
            class="repayment-row"
          >
            <div>
              <strong>{{ repayment.installment_number }}회차</strong
              ><span>{{ formatDate(repayment.due_date) }}</span>
            </div>
            <div class="repayment-value">
              <strong>{{ formatWon(repayment.amount) }}</strong
              ><span class="installment-status" :class="`installment-${repayment.status}`">{{
                repaymentStatusLabel(repayment.status)
              }}</span>
            </div>
          </article>
          <div v-if="overdueCount(activeApplication)" class="overdue-payment">
            <h3>연체 회차 납부</h3>
            <p>
              {{ overdueCount(activeApplication) }}회차가 연체됐어요. 월 상환액의 정수배로 납부할 수
              있어요.
            </p>
            <form class="form-stack" @submit.prevent="repayOverdue(activeApplication)">
              <label class="field-label" for="repayment-amount">납부 금액 (원)</label>
              <input
                id="repayment-amount"
                v-model="repaymentAmount"
                class="text-input"
                type="text"
                inputmode="numeric"
                autocomplete="off"
                :placeholder="String(activeApplication.monthly_installment)"
                required
              />
              <button
                class="button button-primary button-wide"
                type="submit"
                :disabled="submitting"
              >
                {{ submitting ? '처리 중' : '연체금 납부하기' }}
              </button>
            </form>
          </div>
          <p v-else class="inline-empty">현재 연체된 회차가 없습니다.</p>
        </div>
      </section>

      <section class="section-block">
        <div class="section-title-row"><h2>대출 상품</h2></div>
        <p class="section-caption">이자 없이 원금을 나누어 상환하는 데모 상품입니다.</p>
        <div v-if="products.length" class="product-list">
          <button
            v-for="product in products"
            :key="product.id"
            class="product-card surface-card"
            :class="{ chosen: selectedProductId === product.id }"
            type="button"
            :aria-pressed="selectedProductId === product.id"
            @click="selectedProductId = product.id"
          >
            <span class="product-check" aria-hidden="true">{{
              selectedProductId === product.id ? '✓' : ''
            }}</span>
            <span class="product-copy"
              ><strong>{{ product.name }}</strong
              ><small
                >{{ product.term_months }}개월 · 월 상환
                {{ formatWon(product.monthly_installment) }}</small
              ></span
            >
            <strong class="product-principal">{{ formatWon(product.principal_amount) }}</strong>
          </button>
          <button
            class="button button-primary button-wide"
            type="button"
            :disabled="submitting || !selectedProduct || Boolean(activeApplication)"
            @click="applyForLoan"
          >
            {{
              submitting
                ? '신청 중'
                : activeApplication
                  ? '진행 중인 대출이 있어요'
                  : '선택한 상품 신청하기'
            }}
          </button>
        </div>
        <div v-else class="surface-card empty-state">
          <strong>현재 신청할 수 있는 상품이 없어요</strong>
        </div>
      </section>

      <section
        v-if="
          applications.some(
            (application) => application.status === 'repaid' || application.status === 'rejected',
          )
        "
        class="section-block"
      >
        <h2 class="section-title">신청 이력</h2>
        <div class="application-history surface-card">
          <article
            v-for="application in applications.filter(
              (item) => item.status === 'repaid' || item.status === 'rejected',
            )"
            :key="application.id"
            class="history-row"
          >
            <div>
              <strong>{{ application.product_name }}</strong
              ><span>{{ formatWon(application.principal_amount) }}</span>
            </div>
            <span class="status-pill" :class="`status-${application.status}`">{{
              statusLabel(application.status)
            }}</span>
          </article>
        </div>
      </section>
    </template>
  </AppShell>
</template>
