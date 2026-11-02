import assert from 'node:assert/strict';
import test from 'node:test';
import { parseKakaoCallback } from '../../src/lib/kakao.js';

test('parses the authorization code and state from the callback query', () => {
  assert.deepEqual(parseKakaoCallback('?code=sample-code&state=state-1'), {
    code: 'sample-code',
    state: 'state-1',
  });
});

test('returns a safe message when Kakao rejects or omits callback values', () => {
  assert.equal(
    parseKakaoCallback('?error=access_denied').error,
    '카카오 로그인이 취소되었거나 실패했습니다.',
  );
  assert.match(parseKakaoCallback('?code=only-code').error, /다시 시작/);
});
