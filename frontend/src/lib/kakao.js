export function parseKakaoCallback(search) {
  const parameters = new URLSearchParams(search);
  const providerError = parameters.get('error');
  if (providerError) {
    return {
      error: parameters.get('error_description') || '카카오 로그인이 취소되었거나 실패했습니다.',
    };
  }

  const code = parameters.get('code');
  const state = parameters.get('state');
  if (!code || !state) return { error: '로그인 정보가 만료되었습니다. 다시 시작해 주세요.' };
  return { code, state };
}
