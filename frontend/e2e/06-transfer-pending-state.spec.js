import { expect, test } from '@playwright/test';
import { login } from './helpers.js';

test('a pending transfer keeps its recipient and confirmation controls stable', async ({
  page,
}) => {
  await login(page, 'customer', 'customer');
  await page.goto('/transactions?mode=transfer');
  await page
    .getByLabel('받는 분 계좌번호 또는 휴대전화번호')
    .fill(process.env.PODOBANK_UI_RECIPIENT_PHONE);
  await page.getByRole('button', { name: '찾기' }).click();
  const recipient = page.getByRole('button', { name: /검증 수취인/ });
  await expect(recipient).toBeVisible();
  await recipient.click();
  await page.getByLabel('금액 (원)').fill('1000');
  await page.getByRole('button', { name: '송금 금액 확인' }).click();

  let releaseResponse;
  let markTransferStarted;
  const responseGate = new Promise((resolve) => {
    releaseResponse = resolve;
  });
  const transferStarted = new Promise((resolve) => {
    markTransferStarted = resolve;
  });
  await page.route('**/transactions/transfer', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }

    const response = await route.fetch();
    markTransferStarted();
    await responseGate;
    await route.fulfill({ response });
  });

  await page.getByRole('button', { name: '확인하고 송금하기' }).click();
  await transferStarted;

  const depositTab = page.getByRole('tab', { name: '입금' });
  try {
    await expect.soft(depositTab).toBeDisabled();
    await expect.soft(recipient).toBeDisabled();
    if (await depositTab.isEnabled()) await depositTab.click();
  } finally {
    releaseResponse();
  }

  await expect(
    page.getByText('검증 수취인님에게 1,000원을 보냈어요.', { exact: true }),
  ).toBeVisible();
});
