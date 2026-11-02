const amountFormatter = new Intl.NumberFormat('ko-KR');

export function formatAmount(amount) {
  return amountFormatter.format(Number(amount) || 0);
}

export function formatWon(amount) {
  return `${formatAmount(amount)}원`;
}

export function formatLedgerAmount(amount) {
  const value = Number(amount) || 0;
  const sign = value > 0 ? '+' : '';
  return `${sign}${formatAmount(value)}원`;
}

export function parsePositiveAmount(value) {
  const normalized = String(value ?? '').trim();
  if (!/^\d+$/.test(normalized)) return null;
  const amount = Number(normalized);
  return Number.isSafeInteger(amount) && amount > 0 ? amount : null;
}

export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return '—';
  const includeTime = !/^\d{4}-\d{2}-\d{2}$/.test(value);
  return new Intl.DateTimeFormat(
    'ko-KR',
    includeTime
      ? { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Seoul' }
      : { dateStyle: 'medium', timeZone: 'Asia/Seoul' },
  ).format(date);
}
