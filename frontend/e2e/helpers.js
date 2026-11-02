import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect } from '@playwright/test';

export async function login(page, role, fixture) {
  const fixtureKey = fixture.toUpperCase();
  await page.goto('/login');
  await page.getByLabel('휴대전화번호').fill(process.env[`PODOBANK_UI_${fixtureKey}_PHONE`]);
  await page
    .getByLabel('비밀번호', { exact: true })
    .fill(process.env[`PODOBANK_UI_${fixtureKey}_PASSWORD`]);
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await expect(page).toHaveURL(role === 'employee' ? /\/staff\/loans$/ : /\/home$/);

  const cookies = await page.context().cookies(process.env.PODOBANK_UI_API_ORIGIN);
  expect(cookies.some((cookie) => cookie.name === 'podobank_session' && cookie.httpOnly)).toBe(
    true,
  );
  await assertMobileLayout(page);
}

export async function assertMobileLayout(page) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(dimensions.viewport).toBe(384);
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
}

export async function capture(page, filename) {
  const evidenceDir = process.env.PODOBANK_UI_EVIDENCE_DIR;
  mkdirSync(evidenceDir, { recursive: true });
  await page.screenshot({ path: join(evidenceDir, filename), fullPage: true });
}

export async function applyForCarLoan(page) {
  await page.goto('/loans');
  await expect(page.getByRole('heading', { name: '대출', exact: true })).toBeVisible();
  await page.getByRole('button', { name: /자동차 구매/ }).click();
  await page.getByRole('button', { name: '선택한 상품 신청하기' }).click();
  await expect(page.getByText('대출 신청을 접수했어요', { exact: false })).toBeVisible();
  await expect(page.getByText('직원 심사 중')).toBeVisible();
  await assertMobileLayout(page);
}

export async function employeeDecision(page, customerName, decision) {
  await page.getByRole('button', { name: '로그아웃' }).click();
  await login(page, 'employee', 'employee');
  page.on('dialog', (dialog) => dialog.accept());

  const application = page.getByRole('article').filter({ hasText: customerName });
  await expect(application).toBeVisible();
  await application.getByRole('button', { name: decision === 'approve' ? '승인' : '거절' }).click();
  await expect(
    page.getByText(decision === 'approve' ? '신청을 승인했습니다' : '신청을 거절했습니다', {
      exact: false,
    }),
  ).toBeVisible();
  await assertMobileLayout(page);
}

export async function returnToCustomer(page, fixture) {
  await page.getByRole('button', { name: '로그아웃' }).click();
  await login(page, 'customer', fixture);
}
