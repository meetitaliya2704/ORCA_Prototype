export type RiskLevel = "GO" | "WAIT" | "AVOID";

export type UserMode = "fisherman" | "authority" | "researcher" | "operator";

export interface UserModeConfig {
  id: UserMode;
  label: string;
  roleDescription: string;
  badgeColor: string;
  defaultPrompt: string;
  features: string[];
}

export interface OceanConditions {
  waveHeightM: number;
  windSpeedKmh: number;
  windDirection: string;
  seaSurfaceTempC: number;
  rainProbabilityPct: number;
  visibilityKm: number;
  tideLevelM: number;
  currentSpeedKnots: number;
}

export interface RiskFactor {
  label: string;
  value: string;
  percent: number; // 0-100 for visual bar
  level?: RiskLevel;
}

export interface DecisionData {
  status: RiskLevel;
  headline: string;
  riskScore: number; // 0-100
  riskFactors: RiskFactor[];
  summary: string;
  recommendation: string;
  updatedAt: string;
  location: string;
}

export type AgentStatus = "completed" | "processing" | "pending" | "error";

export interface AgentStep {
  name: string;
  status: AgentStatus;
  detail?: string;
  latencyMs?: number;
}

export interface EvidenceSource {
  id: string;
  sourceName: string;
  category: "weather" | "satellite" | "ocean" | "gis" | "ais";
  label: string;
  metric: string;
  confidence: number; // 0-100
  fetchedAgo: string;
  status: "verified" | "live" | "cached";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  decision?: DecisionData;
  agents?: AgentStep[];
  sources?: EvidenceSource[];
  timestamp: string;
  userMode?: UserMode;
}

export interface AlertItem {
  id: string;
  severity: "high" | "medium" | "low";
  title: string;
  region: string;
  issuedAt: string;
  description: string;
  type: "cyclone" | "wave" | "zone" | "traffic" | "biological";
  targetModes: UserMode[];
  coordinates?: string;
}

export interface MapMarker {
  id: string;
  type: "hazard" | "vessel" | "route" | "user" | "sensor" | "port";
  label: string;
  subtitle?: string;
  x: number; // percentage position (0-100)
  y: number;
  severity?: "high" | "medium" | "low";
  details?: {
    speed?: string;
    heading?: string;
    temperature?: string;
    waveHeight?: string;
    warning?: string;
  };
  visibleForModes?: UserMode[];
}

export interface AgentPipelineInfo {
  id: string;
  name: string;
  role: string;
  endpoint: string;
  avgLatency: string;
  status: "operational" | "degraded" | "standby";
  dataFeed: string;
  lastSync: string;
  accuracy: string;
}