import { createRouter, createWebHistory } from 'vue-router';
import { loadSession, session } from './session.js';
import AccountView from './views/AccountView.vue';
import EmployeeLoansView from './views/EmployeeLoansView.vue';
import HomeView from './views/HomeView.vue';
import KakaoCallbackView from './views/KakaoCallbackView.vue';
import LandingView from './views/LandingView.vue';
import LoansView from './views/LoansView.vue';
import LoginView from './views/LoginView.vue';
import NotFoundView from './views/NotFoundView.vue';
import PasswordSetupView from './views/PasswordSetupView.vue';
import SignupView from './views/SignupView.vue';
import TransactionsView from './views/TransactionsView.vue';
import UnavailableView from './views/UnavailableView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'landing', component: LandingView },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/signup', name: 'signup', component: SignupView },
    { path: '/auth/kakao/callback', name: 'kakao-callback', component: KakaoCallbackView },
    { path: '/unavailable', name: 'unavailable', component: UnavailableView },
    { path: '/home', name: 'home', component: HomeView, meta: { role: 'customer' } },
    { path: '/accounts', name: 'account', component: AccountView, meta: { role: 'customer' } },
    {
      path: '/transactions',
      name: 'transactions',
      component: TransactionsView,
      meta: { role: 'customer' },
    },
    { path: '/loans', name: 'loans', component: LoansView, meta: { role: 'customer' } },
    {
      path: '/profile/password',
      name: 'password-setup',
      component: PasswordSetupView,
      meta: { role: 'customer' },
    },
    {
      path: '/staff/loans',
      name: 'employee-loans',
      component: EmployeeLoansView,
      meta: { role: 'bank_employee' },
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView },
  ],
});

router.beforeEach(async (to) => {
  const role = to.meta.role;
  if (role) {
    const user = await loadSession();
    if (!user) {
      if (session.error) return { name: 'unavailable' };
      return { name: 'login', query: { next: to.fullPath } };
    }
    if (user.role !== role) {
      return user.role === 'bank_employee' ? { name: 'employee-loans' } : { name: 'home' };
    }
  }

  if (to.name === 'login' && !session.loaded) await loadSession();
  if (to.name === 'login' && session.user) {
    return session.user.role === 'bank_employee' ? { name: 'employee-loans' } : { name: 'home' };
  }
  return true;
});

export default router;
