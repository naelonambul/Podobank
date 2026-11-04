import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

async function captureEvents(page, fail = false, status = 201) {
  const events = [];
  await page.route('**/events', async (route) => {
    events.push(route.request().postDataJSON());
    if (fail) await route.abort();
    else await route.fulfill({ status, json: { status: 'stored' } });
  });
  return events;
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

test('successful initial, page and back navigations use stable anonymous envelopes', async ({
  page,
}) => {
  const events = await captureEvents(page);
  await page.goto('/');
  await expect.poll(() => events.length).toBe(1);
  await page.getByRole('button', { name: '포도뱅크 시작하기' }).click();
  await expect.poll(() => events.length).toBe(2);
  await page.goBack();
  await expect.poll(() => events.length).toBe(3);
  expect(events.map((event) => event.page.path)).toEqual(['/', '/signup', '/']);
  for (const event of events) {
    expect(event.type).toBe('page_view');
    expect(event.schema_version).toBe(4);
    expect(event.event_id).toMatch(uuid);
    expect(event.session_id).toBe(events[0].session_id);
    expect(event.anonymous_id).toBe(events[0].anonymous_id);
    expect(Object.keys(event.props)).toEqual(['route_name']);
  }
  expect(new Set(events.map((event) => event.event_id)).size).toBe(3);
  await page.reload();
  await expect.poll(() => events.length).toBe(4);
  expect(events[3].session_id).toBe(events[0].session_id);
  expect(events[3].anonymous_id).toBe(events[0].anonymous_id);
  const secondTab = await page.context().newPage();
  const secondEvents = await captureEvents(secondTab);
  await secondTab.goto('/');
  await expect.poll(() => secondEvents.length).toBe(1);
  expect(secondEvents[0].anonymous_id).toBe(events[0].anonymous_id);
  expect(secondEvents[0].session_id).not.toBe(events[0].session_id);
  await secondTab.close();
});

test('guard redirects emit only the final page and strip sensitive URL components', async ({
  page,
}) => {
  const events = await captureEvents(page);
  await page.route('**/auth/me', (route) =>
    route.fulfill({ status: 401, json: { detail: 'authentication required' } }),
  );
  await page.goto('/home?token=secret#fragment');
  await expect(page).toHaveURL(/\/login\?/);
  await expect.poll(() => events.length).toBe(1);
  expect(events[0].page.path).toBe('/login');
  expect(JSON.stringify(events)).not.toContain('secret');
  await page.getByRole('link', { name: '회원가입' }).click();
  await expect.poll(() => events.length).toBe(2);
  expect(events[1].page.referrer).toMatch(/\/login$/);
});

test('blocked storage and event network failure keep signup navigation functional', async ({
  page,
}) => {
  await page.addInitScript(() => {
    for (const name of ['localStorage', 'sessionStorage']) {
      Object.defineProperty(window, name, {
        get() {
          throw new DOMException('blocked', 'SecurityError');
        },
      });
    }
  });
  const events = await captureEvents(page, true);
  await page.goto('/?code=secret#fragment');
  await expect.poll(() => events.length).toBe(1);
  await page.getByRole('button', { name: '포도뱅크 시작하기' }).click();
  await expect(page).toHaveURL(/\/signup$/);
  await expect.poll(() => events.length).toBe(2);
  expect(events[0].anonymous_id).toMatch(uuid);
  expect(events[1].anonymous_id).toBe(events[0].anonymous_id);
  expect(JSON.stringify(events)).not.toContain('secret');
});

test('common trackEvent uses the browser page context and caller properties', async ({ page }) => {
  await captureEvents(page);
  const source = await readFile(new URL('../src/telemetry.js', import.meta.url), 'utf8');
  await page.route('**/telemetry-test-module.js', (route) =>
    route.fulfill({ contentType: 'text/javascript', body: source }),
  );
  await page.goto('/signup?code=private#fragment');
  const sent = await page.evaluate(async () => {
    const { trackEvent } = await import('/telemetry-test-module.js');
    const originalFetch = window.fetch;
    const events = [];
    window.fetch = async (_url, options) => {
      events.push(JSON.parse(options.body));
      return new Response('{}', { status: 503 });
    };
    try {
      trackEvent('product_view', { product_id: 1, category: 'cpu' });
      return events;
    } finally {
      window.fetch = originalFetch;
    }
  });
  expect(sent).toHaveLength(1);
  expect(sent[0].props).toEqual({ product_id: 1, category: 'cpu' });
  expect(sent[0].type).toBe('product_view');
  expect(sent[0].schema_version).toBe(4);
  expect(sent[0].event_id).toMatch(uuid);
  expect(sent[0].page.path).toBe('/signup');
  expect(JSON.stringify(sent)).not.toContain('private');
});

test('HTTP rejection of telemetry does not redirect or disable signup', async ({ page }) => {
  for (const status of [401, 503]) {
    await page.unroute('**/events');
    const events = await captureEvents(page, false, status);
    await page.goto('/signup/phone');
    await expect.poll(() => events.length).toBe(1);
    await expect(page).toHaveURL(/\/signup\/phone$/);
    await page.getByLabel('이름').fill('데모 고객');
    await expect(page.getByLabel('이름')).toHaveValue('데모 고객');
  }
});
