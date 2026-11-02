const API_ORIGIN = (import.meta.env.VITE_API_ORIGIN || 'http://localhost:8000').replace(/\/$/, '');
const ERROR_MESSAGES = {
  active_loan_exists: '신청 중이거나 상환 중인 대출이 있어요.',
  account_not_found: '계좌를 찾을 수 없습니다.',
  application_not_pending: '이미 처리된 대출 신청입니다. 목록을 새로고침해 주세요.',
  balance_limit: '계좌 잔액 한도를 초과하는 처리입니다.',
  insufficient_funds: '잔액이 부족합니다.',
  invalid_amount: '금액은 1원 이상의 정수로 입력해 주세요.',
  kakao_authorization_failed: '카카오 인증에 실패했습니다. 다시 로그인해 주세요.',
  kakao_not_configured: '카카오 로그인이 아직 설정되지 않았습니다.',
  kakao_unavailable: '카카오에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.',
  loan_not_repaying: '현재 상환할 수 있는 대출이 아닙니다.',
  no_overdue_installments: '납부할 연체 회차가 없습니다.',
  password_already_set: '로그인 비밀번호는 한 번만 설정할 수 있습니다.',
  phone_already_registered: '이미 등록된 휴대전화번호입니다.',
  product_not_found: '대출 상품을 찾을 수 없습니다.',
  recipient_not_found: '받는 분 계좌를 찾을 수 없습니다.',
  self_transfer: '본인 계좌로는 송금할 수 없습니다.',
  signup_session_expired: '가입 시간이 만료됐습니다. 카카오 로그인을 다시 시작해 주세요.',
  signup_session_required: '카카오 로그인 후 가입을 이어가 주세요.',
};

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'network_error' } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export async function apiRequest(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' };
  const options = {
    method,
    credentials: 'include',
    headers,
    signal,
  };

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_ORIGIN}${path}`, options);
  } catch {
    throw new ApiError('은행 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    // A non-JSON error response still becomes a safe generic message below.
  }

  if (!response.ok) {
    const detail = payload?.detail;
    let message = '요청을 처리하지 못했습니다. 입력 내용을 확인해 주세요.';
    if (typeof detail === 'string') {
      const knownMessages = {
        'account not found': '계좌를 찾을 수 없습니다.',
        'authentication required': '로그인 시간이 만료됐습니다. 다시 로그인해 주세요.',
        'bank employee access required': '은행 직원 계정으로 로그인해 주세요.',
        'invalid credentials': '로그인 정보를 확인해 주세요.',
        'invalid phone number or password': '휴대전화번호 또는 비밀번호가 올바르지 않습니다.',
      };
      message = knownMessages[detail] || detail;
    } else if (typeof detail?.message === 'string') {
      message = ERROR_MESSAGES[detail.code] || detail.message;
    } else if (Array.isArray(detail)) message = '입력 내용을 확인해 주세요.';
    throw new ApiError(message, {
      status: response.status,
      code: detail?.code || 'request_failed',
    });
  }

  return payload;
}

export const api = {
  get(path, options = {}) {
    return apiRequest(path, options);
  },
  post(path, body, options = {}) {
    return apiRequest(path, { ...options, method: 'POST', body });
  },
};
