import { expect, test } from '@playwright/test';
import { assertMobileLayout, capture, login } from './helpers.js';

test('customer deposits, searches a recipient, transfers, withdraws, and sees the ledger', async ({
  page,
}) => {
  await login(page, 'customer', 'customer');
  await page.goto('/transactions?mode=deposit');
  await page.getByLabel('금액 (원)').fill('1000000');
  await page.getByRole('button', { name: '입금하기' }).click();
  await expect(page.getByRole('status')).toContainText('1,000,000원 거래가 완료됐어요.');

  await page.getByRole('tab', { name: '송금' }).click();
  await page
    .getByLabel('받는 분 계좌번호 또는 휴대전화번호')
    .fill(process.env.PODOBANK_UI_RECIPIENT_PHONE);
  await page.getByRole('button', { name: '찾기' }).click();
  const recipient = page.getByRole('button', { name: /검증 수취인/ });
  await expect(recipient).toBeVisible();
  await recipient.click();
  await page.getByLabel('금액 (원)').fill('250000');
  await page.getByRole('button', { name: '송금 금액 확인' }).click();
  await expect(page.getByRole('status')).toContainText('검증 수취인님에게 250,000원을 보냅니다');
  await page.getByRole('button', { name: '확인하고 송금하기' }).click();
  await expect(page.getByRole('status')).toContainText('검증 수취인님에게 250,000원을 보냈어요.');

  await page.getByRole('tab', { name: '출금' }).click();
  await page.getByLabel('금액 (원)').fill('100000');
  await page.getByRole('button', { name: '출금하기' }).click();
  await expect(page.getByRole('status')).toContainText('100,000원 거래가 완료됐어요.');
  await assertMobileLayout(page);

  await page.getByRole('link', { name: '계좌' }).click();
  const balance = page.getByTestId('account-balance');
  const ledger = page.locator('.transaction-list');
  await expect(balance).toHaveAttribute('data-amount', '650000');
  await expect(ledger.getByText('입금', { exact: true })).toBeVisible();
  await expect(ledger.getByText('보낸 송금', { exact: true })).toBeVisible();
  await expect(ledger.getByText('출금', { exact: true })).toBeVisible();
  await assertMobileLayout(page);
  await capture(page, 'transactions-ledger.png');
});
