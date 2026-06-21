/**
 * TypeScript interfaces matching TrafficVision AI API responses.
 */

export interface BoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface UploadResponse {
  image_id: string;
  object_path: string;
  uploaded_at: string;
}

export interface AnalyzeViolation {
  id: string;
  violation_type: string;
  confidence: number;
  bounding_box: BoundingBox;
  plate_number: string | null;
  annotated_image_path: string | null;
}

export interface AnalyzeVehicle {
  id: string;
  vehicle_class: string;
  bounding_box: BoundingBox;
  plate_number: string | null;
}

export interface AnalyzeResponse {
  image_id: string;
  annotated_image_url: string | null;
  violations: AnalyzeViolation[];
  vehicles: AnalyzeVehicle[];
  processing_time_ms: number;
}

export interface ViolationRecord {
  id: string;
  image_id: string;
  vehicle_id: string | null;
  violation_type: string;
  confidence: number;
  bounding_box: BoundingBox;
  plate_number: string | null;
  annotated_image_path: string | null;
  created_at: string;
}

export interface ViolationsListResponse {
  total_count: number;
  page: number;
  page_size: number;
  results: ViolationRecord[];
}

export interface VehicleDetail {
  id: string;
  vehicle_class: string;
  bounding_box: BoundingBox;
  plate_number: string | null;
}

export interface ViolationDetailResponse {
  id: string;
  image_id: string;
  vehicle: VehicleDetail | null;
  violation_type: string;
  confidence: number;
  bounding_box: BoundingBox;
  plate_number: string | null;
  annotated_image_url: string | null;
  original_image_url: string | null;
  all_vehicles?: VehicleDetail[];
  created_at: string;
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface AnalyticsResponse {
  window_start: string;
  window_end: string;
  by_type: Record<string, number>;
  by_date: DailyCount[];
  total: number;
  cached: boolean;
}

export interface HealthResponse {
  status: string;
  database: string;
  storage: string;
  timestamp: string;
}

export type ViolationType =
  | 'HELMET_NON_COMPLIANCE'
  | 'TRIPLE_RIDING'
  | 'WRONG_SIDE_DRIVING'
  | 'STOP_LINE_VIOLATION'
  | 'ILLEGAL_PARKING';

export interface ViolationFilters {
  violation_type?: string;
  plate_number?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  page_size?: number;
}
