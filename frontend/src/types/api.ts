/** Contratos de la API FastAPI (espejo de src/api/schemas). */

export type UserRole = 'ADMIN' | 'SUPERVISOR' | 'WORKER';
export type IncidentStatus = 'PENDING' | 'APPROVED' | 'REJECTED';
export type FileStatus = 'PENDING' | 'PROCESSED' | 'FAILED';

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserProfile {
  id: string;
  organization_id: string;
  organization_name?: string | null;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  employee_id: string | null;
  employee_code: string | null;
  first_name?: string | null;
  last_name?: string | null;
  weekly_contract_hours?: number | null;
}

export interface PunchStatusResponse {
  status: 'IN_PROGRESS' | 'IDLE';
  active_record: AttendanceRecord | null;
  last_punch: string | null;
}

export interface AttendanceRecordUpdateRequest {
  punch_in: string;
  punch_out: string;
  reason?: string;
}

export interface UserProfileUpdateRequest {
  first_name: string;
  last_name: string;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

export interface Incident {
  id: string;
  reason: string;
  status: IncidentStatus;
  supervisor_id: string | null;
  reviewed_at: string | null;
}

export interface AttendanceRecord {
  id: string;
  employee_code: string;
  date: string;
  punch_in: string | null;
  punch_out: string | null;
  ordinary_hours: number;
  night_hours: number;
  holiday_hours: number;
  excess_hours: number;
  has_incident: boolean;
  incidents: Incident[];
}

export interface SummaryItem {
  employee_code: string;
  total_hours: number;
  ordinary_hours: number;
  night_hours: number;
  holiday_hours: number;
  excess_hours: number;
  incidents_count: number;
}

export interface AttendanceSummary {
  organization_id: string;
  total_records: number;
  total_hours: number;
  total_incidents: number;
  items: SummaryItem[];
}

export interface UploadResult {
  file_id: string;
  filename: string;
  total_rows_processed: number;
  reconciled_shifts: number;
  incidents_detected: number;
  status: FileStatus;
}

export interface IncidentJustifyPayload {
  reason: string;
  status: Exclude<IncidentStatus, 'PENDING'>;
}

export interface RecordFilters {
  employee_code?: string;
  date_from?: string;
  date_to?: string;
  only_incidents?: boolean;
}

export interface BulkChangeItem {
  change_type: 'MODIFIED' | 'NEW' | 'UNCHANGED';
  record_id: string | null;
  employee_code: string;
  employee_name: string | null;
  date: string;
  old_punch_in: string | null;
  old_punch_out: string | null;
  old_ordinary_hours: number;
  old_excess_hours: number;
  new_punch_in: string;
  new_punch_out: string;
  new_ordinary_hours: number;
  new_excess_hours: number;
}

export interface BulkDiffPreview {
  total_rows_inspected: number;
  changes_count: number;
  new_records_count: number;
  modified_records_count: number;
  unchanged_count: number;
  changes: BulkChangeItem[];
}

export interface BulkApplyPayload {
  changes: BulkChangeItem[];
  audit_reason: string;
}

