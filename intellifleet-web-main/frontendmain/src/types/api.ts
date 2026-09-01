// API Response Types

// Chat History Types
export interface ChatHistoryResponse {
  success: boolean;
  message: string;
  data: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
}

export interface ApiResponse<T = any> {
  success: boolean;
  message?: string;
  data?: T;
  error?: string;
}

// Auth Types
export interface User {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  provider?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
}

export interface AuthResponse {
  token: string;
}

// Warehouse Types
// Warehouse Types
export interface Warehouse {
  id: number;                // Map from warehouse_id
  warehouse_id?: number;     // Keep original field for reference
  user_id?: number;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  country?: string;
  city?: string;
  node_type?: string;
  is_active?: number;
  vehicles?: VehicleCount;
  created_at?: string;
  updated_at?: string;
  inventory?: number;
  reorder_level?: number;
}

export interface VehicleCount {
  trucks: number;
  autos: number;
  bikes: number;
  cars: number;
}

// Vehicle Types
export interface Vehicle {
  id: number;
  warehouse_id: number;
  type: 'truck' | 'car' | 'bike' | 'auto' | 'plane';
  label: string;
  current_location: string;
  current_position: {
    lat: number;
    lng: number;
  };
  is_available: boolean;
  status: 'available' | 'assigned' | 'completed' | 'disrupted';
  assigned_route?: RouteAssignment;
  departure_time?: string;
  schedule_departure_time?: string;
  arrival_time?: string;
  capacity?: number;
  warehouse_name?: string;
  vehicle_details?: {
    speed?: number;
    fuel_type?: string;
    fuel_consumption?: number;
    fuel_price?: number;
  };
}

export interface RouteAssignment {
  route_id: number;
  route_data: any;
  waypoints: string[];
  source: string;
  destination: string;
  intermediate_locations: string[];
  assigned_at: string;
  vehicle_type: string;
  vehicle_details?: {
    speed?: number;
    capacity?: string;
    fuel_type?: string;
    fuel_consumption?: number;
    fuel_price?: number;
  };
  route_cost?: string | null;
  distance?: number | null;
  departure_time?: string;
  arrival_time?: string;
}

// Route Types
// export interface RouteRequest {
//   source: string;
//   destination: string;
// }

// export interface MultiRouteRequest {
//   source: string;
//   destination: string;
//   intermediate_locations?: string[];
//   waypoints?: string[];
// }

export interface RoutePoint {
  lat: number;
  lng: number;
}

export interface Route {
  path: RoutePoint[] | string;  // Can be array of lat/lng OR encoded polyline string
  distance: string;
  duration: string;
  summary: string;
  overview_polyline?: string;
  isOptimal?: boolean;
}

// export interface RouteResponse {
//   source: string;
//   destination: string;
//   source_coords: RoutePoint;
//   dest_coords: RoutePoint;
//   optimal_routes: Route[];
//   total_routes: number;
//   route_id?: number; // Added route_id
// }

// export interface MultiRouteResponse {
//   segments?: RouteSegment[];
//   locations: string[];
//   total_segments?: number;
//   combined_route?: Route;
//   optimal_routes: Route[];
//   route_id?: number; // Added route_id
// }

// export interface RouteSegment {
//   from: string;
//   to: string;
//   routes: Route[];
// }

// Chat/AI Types
export interface ChatPrompt {
  prompt: string;
}

// New Chat Types for /agent endpoint
export interface ChatMessage {
  type: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  data?: any;
}

export interface ChatAction {
  type: 'display_route' | 'plan_route' | 'assign_vehicles' | 'list_vehicles' |
  'clear_chat' | 'clear_map' | 'satellite_view' | 'street_view' |
  'remove_route' | 'alternative_route' | 'reset_vehicle' | 'multimodal_route' | "assign_vehicle_multimodal" | "remove_multimodal_route" | "connect_hub" | "warehouse_status_update" | "reset_all_vehicles" | "fetch_routes" | "assign_plane" | "vehicle_status_update" | "route_status_update" | "air_intermediate_route" | "partial_assignment_start" | "animate_segment" | "manage_disruption_tool";
  data?: any;
}

export interface ChatResponse {
  response: string;
  session_id: string;
  messages: ChatMessage[];
  actions: ChatAction[];
  data?: any;
}

// Legacy types (kept if needed for reference, but likely unused now)
// export interface ExtractedRoute {
//   source?: string;
//   destination?: string;
//   intermediate_locations?: string[];
//   confidence: number;
//   error?: string;
// }

// export interface IntentAnalysis {
//   intent: string;
//   parameters: Record<string, any>;
//   confidence: number;
//   reply?: string;
// }

// CSV Upload Types
// export interface UploadResponse {
//   message: string;
//   data: Warehouse[];
//   total_warehouses: number;
//   total_vehicles: number;
//   failed_geocoding?: string[];
// }

export interface UploadResponse {
  upload_type: 'warehouse' | 'vehicle';
  success: boolean;
  message: string;
  data?: Warehouse[];  // Only present for warehouse upload
  total_warehouses?: number;
  total_vehicles?: number;
  missing_warehouses?: string[];  // Only present for vehicle upload
  failed_geocoding?: string[];
}

export interface ActiveRoute {
  id: number;
  displayId?: string;
  source: string;
  destination: string;
  intermediates: string[];
  waypoints: string[];
  created: Date;
  routeData?: any;
  isActive?: boolean;// Store full route response
}

// Warehouse Inventory Types
export interface WarehouseInventory {
  warehouse_id: number;
  warehouse_name: string;
  inventory: number;
  reorder_level: number;
}

export interface InventoryResponse {
  status: boolean;
  message: string;
  data: WarehouseInventory[];
}

// Vehicle Completion Types
export interface VehicleCompletePayload {
  route_id: number;
  vehicle_id: number;
  destination: string;
}

export interface VehicleCompleteResponse {
  success: boolean;
  message: string;
  status_code: number;
  data: {
    message: string;
    vehicle_id: number;
    destination: string;
    route_id: number;
  };
}

// Route Session Types
export interface RouteSessionResponse {
  success: boolean;
  message: string;
  status_code: number;
  data: {
    routes: any[];
    alternative_routes: any[];
    multimodal_routes: any[];
  };
}