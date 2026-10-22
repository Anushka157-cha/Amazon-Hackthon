import {
  ApproveResponse,
  DiagnosisInfo,
  ProposalInfo,
  RollbackResponse,
  SystemStatusResponse,
} from './types';

// Dynamically connect to the backend on the same host (supports localhost, 127.0.0.1, and LAN IP like 172.18.24.58)
const getBackendUrl = (): string => {
  if (typeof window !== 'undefined' && (window as any).__BACKEND_URL__) {
    return (window as any).__BACKEND_URL__;
  }
  if (typeof window !== 'undefined' && window.location && window.location.hostname) {
    const protocol = window.location.protocol || 'http:';
    const host = window.location.hostname;
    return `${protocol}//${host}:8000`;
  }
  return 'http://127.0.0.1:8000';
};

const BACKEND_URL = getBackendUrl();

export async function fetchStatus(): Promise<SystemStatusResponse> {
  const res = await fetch(`${BACKEND_URL}/api/status`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Failed to fetch status`);
  }
  return res.json();
}

export async function fetchDiagnosis(): Promise<DiagnosisInfo> {
  const res = await fetch(`${BACKEND_URL}/api/diagnosis`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Failed to fetch diagnosis`);
  }
  return res.json();
}

export async function fetchProposal(): Promise<ProposalInfo> {
  const res = await fetch(`${BACKEND_URL}/api/proposal`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Failed to fetch proposal`);
  }
  return res.json();
}

export async function approveFix(
  incidentId?: string,
  userConfirmed: boolean = true
): Promise<ApproveResponse> {
  const res = await fetch(`${BACKEND_URL}/api/approve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      incident_id: incidentId || null,
      user_confirmed: userConfirmed,
    }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Approve fix request failed`);
  }
  return res.json();
}

export async function rollbackFix(incidentId?: string): Promise<RollbackResponse> {
  const res = await fetch(`${BACKEND_URL}/api/rollback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      incident_id: incidentId || null,
    }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Rollback fix request failed`);
  }
  return res.json();
}

export async function injectFailure(
  deviceId: string = 'wifi_extender',
  mode: string = 'offline'
): Promise<any> {
  const res = await fetch(`${BACKEND_URL}/api/inject_failure`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      device_id: deviceId,
      mode: mode,
    }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Inject failure failed`);
  }
  return res.json();
}

export async function clearFailures(): Promise<any> {
  const res = await fetch(`${BACKEND_URL}/api/clear_failures`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: Clear failures failed`);
  }
  return res.json();
}
