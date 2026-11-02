import { expect, test } from '@playwright/test';
import {
  applyForCarLoan,
  assertMobileLayout,
  capture,
  employeeDecision,
  login,
  returnToCustomer,
} from './helpers.js';

test('employee rejects a pending loan and the customer sees the application history', async ({
  page,
}) => {
  await login(page, 'customer', 'rejection');
  await applyForCarLoan(page);
  await employeeDecision(page, '검증 거절 고객', 'reject');
  await returnToCustomer(page, 'rejection');
  await page.goto('/loans');
  await expect(page.locator('.application-history')).toContainText('거절');
  await assertMobileLayout(page);
  await capture(page, 'loan-rejected-history.png');
});
