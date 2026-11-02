import { expect, test } from '@playwright/test';
import { assertMobileLayout, capture, login } from './helpers.js';

test('customer funds the account and pays an overdue installment', async ({ page }) => {
  await login(page, 'customer', 'overdue');
  await page.goto('/loans');
  await expect(page.getByText('연체 회차 납부', { exact: true })).toBeVisible();
  await expect(page.getByText('1회차', { exact: true })).toBeVisible();
  await expect(page.getByText('연체', { exact: true })).toBeVisible();
  await assertMobileLayout(page);
  await capture(page, 'loan-overdue-before-payment.png');

  await page.getByRole('link', { name: '거래' }).click();
  await page.getByLabel('금액 (원)').fill('500000');
  await page.getByRole('button', { name: '입금하기' }).click();
  await expect(page.getByRole('status')).toContainText('500,000원 거래가 완료됐어요.');

  await page.getByRole('link', { name: '대출' }).click();
  await page.getByLabel('납부 금액 (원)').fill('500000');
  await page.getByRole('button', { name: '연체금 납부하기' }).click();
  await expect(page.getByText('연체 회차를 납부했어요.', { exact: false })).toBeVisible();
  await expect(page.locator('.repayment-list')).toContainText('납부 완료');
  await expect(page.getByText('현재 연체된 회차가 없습니다.')).toBeVisible();
  await assertMobileLayout(page);
  await capture(page, 'loan-overdue-paid.png');

  await page.goto('/accounts');
  await expect(page.getByTestId('account-balance')).toHaveAttribute('data-amount', '0');
  await expect(page.getByText('대출 상환', { exact: true })).toBeVisible();
});
