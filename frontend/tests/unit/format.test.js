import assert from 'node:assert/strict';
import test from 'node:test';
import { formatLedgerAmount, formatWon, parsePositiveAmount } from '../../src/lib/format.js';

test('formats won amounts with Korean grouping', () => {
  assert.equal(formatWon(1234567), '1,234,567원');
});

test('formats ledger directions with an explicit plus sign for deposits', () => {
  assert.equal(formatLedgerAmount(5000), '+5,000원');
  assert.equal(formatLedgerAmount(-2500), '-2,500원');
});

test('accepts only positive safe integer amounts', () => {
  assert.equal(parsePositiveAmount('10000'), 10000);
  assert.equal(parsePositiveAmount('0'), null);
  assert.equal(parsePositiveAmount('1.5'), null);
  assert.equal(parsePositiveAmount('9007199254740992'), null);
});
