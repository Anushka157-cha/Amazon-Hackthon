export type DeviceStatus = 'online' | 'degraded' | 'offline';

export interface DeviceInfo {
  id: string;
  name: string;
  status: DeviceStatus;
  device_type: string;
  simulated: boolean;
  upstream: string[];
  downstream: string[];
}

export interface DiagnosisInfo {
  simulated: boolean;
  has_incident: boolean;
  root_cause: string | null;
  root_cause_name: string | null;
  root_cause_status: DeviceStatus | null;
  victims: string[];
  victim_names: string[];
  confidence: number;
  summary: string;
  explanation: string;
  spoken: string;
}

export interface FixImpact {
  target_device: string;
  action: string;
  tier: 'LOW' | 'MEDIUM' | 'HIGH';
  duration_seconds: number;
  affected_devices: string[];
  affected_device_names: string[];
  description: string;
}

export interface ProposalInfo {
  simulated: boolean;
  has_proposal: boolean;
  incident_id: string | null;
  target_device: string | null;
  action: string | null;
  proposed_fix: string | null;
  state: string;
  impact: FixImpact | null;
  devices_affected: string[];
  affected_device_names: string[];
  duration_seconds: number;
  tier: 'LOW' | 'MEDIUM' | 'HIGH' | null;
  confirmation_required: boolean;
  description?: string;
  spoken?: string;
  message?: string;
}

export interface IncidentInfo {
  incident_id: string;
  timestamp: string;
  root_cause: string;
  victims: string[];
  action: string;
  target_device: string;
  state: 'PROPOSED' | 'EXECUTED' | 'RESOLVED' | 'REJECTED' | 'ROLLED_BACK';
  pre_fix_snapshot?: Record<string, string>;
  impact: FixImpact;
}

export interface SystemStatusResponse {
  simulated: boolean;
  devices: Record<string, DeviceInfo>;
  dependency_graph?: Record<string, { upstream: string[]; downstream: string[] }>;
  diagnosis: DiagnosisInfo;
  incidents: Record<string, IncidentInfo>;
  audit_log: Array<{
    timestamp: string;
    actor: string;
    action: string;
    target: string;
    result: any;
  }>;
}

export interface ApproveResponse {
  simulated: boolean;
  incident_id: string;
  executed: boolean;
  target_device?: string;
  message?: string;
  spoken?: string;
  verified?: boolean;
  auto_rollback?: boolean;
  verification?: {
    verified: boolean;
    ticks_passed: number;
    required_ticks: number;
    auto_rollback?: boolean;
    spoken?: string;
  };
  error?: string;
}

export interface RollbackResponse {
  simulated: boolean;
  incident_id: string | null;
  rolled_back: boolean;
  spoken?: string;
  message?: string;
  error?: string;
}
