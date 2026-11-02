<script setup>
import { onMounted, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import MessageBanner from '../components/MessageBanner.vue';
import PageHeading from '../components/PageHeading.vue';
import { api } from '../api.js';
import { formatDate, formatWon } from '../lib/format.js';

const applications = ref([]);
const loading = ref(true);
const busyId = ref(null);
const error = ref('');
const success = ref('');

async function loadPending() {
  loading.value = true;
  error.value = '';
  try {
    const response = await api.get('/loans/pending?limit=50&offset=0');
    applications.value = response.items;
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    loading.value = false;
  }
}

async function review(application, decision) {
  const action = decision === 'approve' ? '승인' : '거절';
  if (
    !window.confirm(
      `${application.customer_name} 고객의 ${application.product_name} 신청을 ${action}할까요?`,
    )
  ) {
    return;
  }

  busyId.value = application.id;
  error.value = '';
  success.value = '';
  try {
    await api.post(`/loans/${application.id}/${decision}`);
    success.value = `${application.customer_name} 고객의 신청을 ${action}했습니다.`;
    await loadPending();
  } catch (requestError) {
    error.value = requestError.message;
  } finally {
    busyId.value = null;
  }
}

onMounted(loadPending);
</script>

<template>
  <AppShell title="대출 심사">
    <PageHeading title="대출 심사" description="고객이 신청한 대출을 확인하고 처리하세요." />
    <MessageBanner :message="error" />
    <MessageBanner :message="success" kind="success" />

    <section v-if="loading" class="loading-card" role="status">
      심사 대상을 불러오고 있어요.
    </section>
    <section v-else class="section-block">
      <div class="section-title-row">
        <h2>심사 대기</h2>
        <button
          class="icon-button"
          type="button"
          aria-label="심사 목록 새로고침"
          @click="loadPending"
        >
          ↻
        </button>
      </div>
      <div v-if="applications.length" class="employee-application-list">
        <article
          v-for="application in applications"
          :key="application.id"
          class="surface-card employee-application"
        >
          <div class="employee-card-header">
            <span class="status-pill status-pending">심사 대기</span>
            <span class="muted-label">신청 {{ formatDate(application.created_at) }}</span>
          </div>
          <h3>{{ application.customer_name }} 고객</h3>
          <p class="employee-product">
            {{ application.product_name }} · {{ application.product_code }}
          </p>
          <dl class="employee-loan-details">
            <div>
              <dt>신청 원금</dt>
              <dd>{{ formatWon(application.principal_amount) }}</dd>
            </div>
            <div>
              <dt>상환 기간</dt>
              <dd>{{ application.term_months }}개월</dd>
            </div>
            <div>
              <dt>월 상환액</dt>
              <dd>{{ formatWon(application.monthly_installment) }}</dd>
            </div>
          </dl>
          <div class="employee-actions">
            <button
              class="button button-outline"
              type="button"
              :disabled="busyId === application.id"
              @click="review(application, 'reject')"
            >
              거절
            </button>
            <button
              class="button button-primary"
              type="button"
              :disabled="busyId === application.id"
              @click="review(application, 'approve')"
            >
              {{ busyId === application.id ? '처리 중' : '승인' }}
            </button>
          </div>
        </article>
      </div>
      <div v-else class="surface-card empty-state">
        <span class="empty-icon" aria-hidden="true">✓</span>
        <strong>심사 대기 중인 신청이 없습니다</strong>
        <p>새 신청이 들어오면 이곳에 표시됩니다.</p>
      </div>
    </section>
  </AppShell>
</template>
