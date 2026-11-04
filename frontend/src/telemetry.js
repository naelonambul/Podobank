const API_ORIGIN = (import.meta.env?.VITE_API_ORIGIN || 'http://localhost:8000').replace(/\/$/, '');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const memoryIds = {};
let pageContext;

function identifier(kind, storageName) {
  if (memoryIds[kind]) return memoryIds[kind];
  let storage;
  try {
    storage = globalThis[storageName];
    const saved = storage?.getItem(`podobank.events.${kind}`);
    if (saved && UUID.test(saved)) return (memoryIds[kind] = saved);
  } catch {
    // Browsers may deny access to storage; retain an ID in this module instead.
  }
  const created = globalThis.crypto.randomUUID();
  memoryIds[kind] = created;
  try {
    storage?.setItem(`podobank.events.${kind}`, created);
  } catch {
    // Navigation must not depend on persistent browser storage.
  }
  return created;
}

function cleanPath(path) {
  const value = new URL(path || '/', globalThis.location?.origin || 'http://localhost');
  return value.pathname.slice(0, 2048);
}

function cleanReferrer(value) {
  if (!value) return '';
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol)) return '';
    const cleaned = `${url.origin}${url.pathname}`;
    return cleaned.length <= 2048 ? cleaned : '';
  } catch {
    return '';
  }
}

function boundedProps(props) {
  let keys = 0;
  function visit(value, depth) {
    if (value !== null && typeof value === 'object') {
      if (depth > 4) throw new Error('props depth');
      if (!Array.isArray(value)) {
        if (Object.getPrototypeOf(value) !== Object.prototype)
          throw new Error('JSON object required');
        keys += Object.keys(value).length;
        if (keys > 64) throw new Error('props keys');
      }
      for (const child of Object.values(value)) visit(child, depth + 1);
    } else if (!['string', 'number', 'boolean'].includes(typeof value) && value !== null) {
      throw new Error('JSON value required');
    } else if (typeof value === 'number' && !Number.isFinite(value)) {
      throw new Error('finite number required');
    }
  }
  if (!props || Array.isArray(props) || typeof props !== 'object') throw new Error('props object');
  visit(props, 1);
  const serialized = JSON.stringify(props);
  if (new TextEncoder().encode(serialized).length > 8192) throw new Error('props size');
  return JSON.parse(serialized);
}

export function trackEvent(type, props = {}) {
  try {
    if (typeof type !== 'string' || !/^[a-z][a-z0-9_]{0,63}$/.test(type)) return;
    const event = {
      event_id: globalThis.crypto.randomUUID(),
      type,
      occurred_at: new Date().toISOString(),
      session_id: identifier('session_id', 'sessionStorage'),
      anonymous_id: identifier('anonymous_id', 'localStorage'),
      page: pageContext || {
        path: cleanPath(globalThis.location?.pathname),
        referrer: cleanReferrer(globalThis.document?.referrer),
      },
      props: boundedProps(props),
      schema_version: 4,
    };
    const body = JSON.stringify(event);
    if (new TextEncoder().encode(body).length > 32768) return;
    Promise.resolve(
      globalThis.fetch(`${API_ORIGIN}/events`, {
        method: 'POST',
        credentials: 'omit',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        keepalive: true,
        body,
      }),
    ).catch(() => {});
  } catch {
    // Telemetry is best effort and must never interrupt the application.
  }
}

export function trackPageView(to, from) {
  try {
    pageContext = {
      path: cleanPath(to.path),
      referrer: from.matched?.length
        ? cleanReferrer(`${globalThis.location.origin}${from.path}`)
        : cleanReferrer(globalThis.document?.referrer),
    };
    trackEvent('page_view', { route_name: String(to.name || 'unknown') });
  } catch {
    // Even malformed navigation context must not affect routing.
  }
}
