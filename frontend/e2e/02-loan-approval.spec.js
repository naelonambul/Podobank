import { expect, test } from '@playwright/test';
import {
  applyForCarLoan,
  assertMobileLayout,
  capture,
  employeeDecision,
  login,
  returnToCustomer,
} from './helpers.js';

test('customer applies for a loan, employee approves it, and the account and schedule update', async ({
  page,
}) => {
  await login(page, 'customer', 'approval');
  await applyForCarLoan(page);
  await capture(page, 'loan-pending-review.png');

  await employeeDecision(page, '검증 승인 고객', 'approve');
  await returnToCustomer(page, 'approval');
  await page.goto('/loans');
  await expect(page.getByText('상환 중')).toBeVisible();
  await expect(page.getByRole('heading', { name: '상환 일정', exact: true })).toBeVisible();
  await expect(page.getByText('1회차', { exact: true })).toBeVisible();
  await assertMobileLayout(page);

  await page.goto('/accounts');
  await expect(page.getByTestId('account-balance')).toHaveAttribute('data-amount', '30000000');
  await expect(page.getByText('대출 실행', { exact: true })).toBeVisible();
  await capture(page, 'loan-approved-account.png');
});
