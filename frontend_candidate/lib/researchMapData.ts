export type ResearchLayerType = "sst" | "salinity" | "chlorophyll" | "anomalies" | "trends";

export interface ResearchStation {
  id: string;
  name: string;
  longitude: number;
  latitude: number;
  depth: string;
  sst: string;
  salinity: string;
  chlorophyll: string;
  anomalies: string;
  trends: string;
  sstColor: string;
  salinityColor: string;
  chlorophyllColor: string;
  anomalyColor: string;
  trendColor: string;
}

export interface ResearchZone {
  id: string;
  name: string;
  coordinates: [number, number][];
  color: Record<ResearchLayerType, string>;
  fillOpacity: Record<ResearchLayerType, number>;
  stroke: Record<ResearchLayerType, string>;
  label: Record<ResearchLayerType, string>;
}

export const RESEARCH_STATIONS: ResearchStation[] = [
  {
    id: "veraval-buoy",
    name: "Veraval Buoy (INCOIS CB-02)",
    longitude: 70.36,
    latitude: 20.89,
    depth: "42m",
    sst: "28.6°C",
    salinity: "35.8 PSU",
    chlorophyll: "1.12 mg/m³",
    anomalies: "+0.8°C",
    trends: "+0.14°C/dec",
    sstColor: "#F59E0B",
    salinityColor: "#3B82F6",
    chlorophyllColor: "#10B981",
    anomalyColor: "#F97316",
    trendColor: "#F59E0B",
  },
  {
    id: "porbandar-station",
    name: "Porbandar Coastal Buoy",
    longitude: 69.58,
    latitude: 21.62,
    depth: "36m",
    sst: "28.2°C",
    salinity: "36.1 PSU",
    chlorophyll: "0.95 mg/m³",
    anomalies: "+0.5°C",
    trends: "+0.13°C/dec",
    sstColor: "#F59E0B",
    salinityColor: "#7C3AED",
    chlorophyllColor: "#10B981",
    anomalyColor: "#FBBF24",
    trendColor: "#F59E0B",
  },
  {
    id: "okha-headland",
    name: "Okha Headland (Gulf Mouth)",
    longitude: 69.06,
    latitude: 22.46,
    depth: "28m",
    sst: "27.8°C",
    salinity: "36.5 PSU",
    chlorophyll: "2.42 mg/m³",
    anomalies: "+0.3°C",
    trends: "+0.12°C/dec",
    sstColor: "#06B6D4",
    salinityColor: "#7C3AED",
    chlorophyllColor: "#059669",
    anomalyColor: "#06B6D4",
    trendColor: "#3B82F6",
  },
  {
    id: "gulf-khambhat",
    name: "Gulf of Khambhat Marine Sensor",
    longitude: 72.15,
    latitude: 21.28,
    depth: "22m",
    sst: "29.8°C",
    salinity: "34.6 PSU",
    chlorophyll: "1.85 mg/m³",
    anomalies: "+1.6°C",
    trends: "+0.18°C/dec",
    sstColor: "#EF4444",
    salinityColor: "#0D9488",
    chlorophyllColor: "#EAB308",
    anomalyColor: "#EF4444",
    trendColor: "#EF4444",
  },
  {
    id: "offshore-basin",
    name: "Offshore Deep Basin (SW Saurashtra)",
    longitude: 68.60,
    latitude: 19.85,
    depth: "1420m",
    sst: "29.1°C",
    salinity: "36.4 PSU",
    chlorophyll: "0.24 mg/m³",
    anomalies: "+0.9°C",
    trends: "+0.15°C/dec",
    sstColor: "#F97316",
    salinityColor: "#7C3AED",
    chlorophyllColor: "#3B82F6",
    anomalyColor: "#F97316",
    trendColor: "#F59E0B",
  },
  {
    id: "mumbai-shelf",
    name: "Mumbai Continental Shelf Buoy",
    longitude: 72.35,
    latitude: 19.12,
    depth: "68m",
    sst: "29.0°C",
    salinity: "35.2 PSU",
    chlorophyll: "0.82 mg/m³",
    anomalies: "+1.1°C",
    trends: "+0.16°C/dec",
    sstColor: "#F97316",
    salinityColor: "#3B82F6",
    chlorophyllColor: "#10B981",
    anomalyColor: "#EF4444",
    trendColor: "#F97316",
  },
  {
    id: "diu-coastal",
    name: "Diu Coastal Observatory",
    longitude: 70.98,
    latitude: 20.70,
    depth: "31m",
    sst: "28.4°C",
    salinity: "35.9 PSU",
    chlorophyll: "1.05 mg/m³",
    anomalies: "+0.7°C",
    trends: "+0.14°C/dec",
    sstColor: "#F59E0B",
    salinityColor: "#3B82F6",
    chlorophyllColor: "#10B981",
    anomalyColor: "#F59E0B",
    trendColor: "#F59E0B",
  },
  {
    id: "jafrabad-deep",
    name: "Jafrabad Deep Channel",
    longitude: 71.40,
    latitude: 20.80,
    depth: "48m",
    sst: "28.5°C",
    salinity: "35.7 PSU",
    chlorophyll: "1.30 mg/m³",
    anomalies: "+0.9°C",
    trends: "+0.15°C/dec",
    sstColor: "#F59E0B",
    salinityColor: "#3B82F6",
    chlorophyllColor: "#10B981",
    anomalyColor: "#F97316",
    trendColor: "#F59E0B",
  },
];

export const RESEARCH_ZONES: ResearchZone[] = [
  {
    id: "upwelling-coastal",
    name: "Saurashtra Coastal Upwelling & Inner Shelf",
    coordinates: [
      [68.7, 22.7],
      [69.4, 22.2],
      [70.2, 21.2],
      [71.2, 20.7],
      [70.9, 19.9],
      [69.8, 20.3],
      [68.6, 21.6],
      [68.7, 22.7],
    ],
    color: {
      sst: "#06B6D4",
      salinity: "#3B82F6",
      chlorophyll: "#10B981",
      anomalies: "#F59E0B",
      trends: "#F59E0B",
    },
    fillOpacity: {
      sst: 0.28,
      salinity: 0.22,
      chlorophyll: 0.32,
      anomalies: 0.24,
      trends: 0.22,
    },
    stroke: {
      sst: "#06B6D4",
      salinity: "#3B82F6",
      chlorophyll: "#10B981",
      anomalies: "#F59E0B",
      trends: "#F59E0B",
    },
    label: {
      sst: "Upwelling Shelf (27.8°C – 28.2°C)",
      salinity: "Coastal Haline Zone (35.8 – 36.2 PSU)",
      chlorophyll: "Eutrophic Coastal Bloom (1.2 – 2.4 mg/m³)",
      anomalies: "Moderate Departure (+0.5°C to +0.8°C)",
      trends: "Historical Decadal Trend (+0.13°C/dec)",
    },
  },
  {
    id: "khambhat-plume",
    name: "Gulf of Khambhat Estuarine Plume & Warm Pool",
    coordinates: [
      [71.6, 22.0],
      [72.7, 21.9],
      [72.9, 21.3],
      [72.6, 20.6],
      [71.7, 20.7],
      [71.4, 21.4],
      [71.6, 22.0],
    ],
    color: {
      sst: "#EF4444",
      salinity: "#0D9488",
      chlorophyll: "#EAB308",
      anomalies: "#DC2626",
      trends: "#EF4444",
    },
    fillOpacity: {
      sst: 0.32,
      salinity: 0.26,
      chlorophyll: 0.34,
      anomalies: 0.32,
      trends: 0.28,
    },
    stroke: {
      sst: "#EF4444",
      salinity: "#0D9488",
      chlorophyll: "#EAB308",
      anomalies: "#DC2626",
      trends: "#EF4444",
    },
    label: {
      sst: "Shallow Warm Pool (29.8°C)",
      salinity: "Riverine Brackish Plume (34.6 PSU)",
      chlorophyll: "Nutrient-Rich Estuary (1.85 mg/m³)",
      anomalies: "Elevated Hotspot (+1.6°C)",
      trends: "Fast Warming Corridor (+0.18°C/dec)",
    },
  },
  {
    id: "mumbai-shelf-zone",
    name: "Mumbai & Konkan Continental Shelf",
    coordinates: [
      [71.5, 20.0],
      [72.8, 19.9],
      [73.0, 18.6],
      [72.0, 18.5],
      [71.2, 19.3],
      [71.5, 20.0],
    ],
    color: {
      sst: "#F97316",
      salinity: "#3B82F6",
      chlorophyll: "#10B981",
      anomalies: "#EF4444",
      trends: "#F97316",
    },
    fillOpacity: {
      sst: 0.26,
      salinity: 0.22,
      chlorophyll: 0.26,
      anomalies: 0.28,
      trends: 0.24,
    },
    stroke: {
      sst: "#F97316",
      salinity: "#3B82F6",
      chlorophyll: "#10B981",
      anomalies: "#EF4444",
      trends: "#F97316",
    },
    label: {
      sst: "Continental Shelf Water (29.0°C)",
      salinity: "Open Shelf Salinity (35.2 PSU)",
      chlorophyll: "Intermediate Biomass (0.82 mg/m³)",
      anomalies: "Thermal Departure (+1.1°C)",
      trends: "Warming Rate (+0.16°C/dec)",
    },
  },
  {
    id: "deep-pelagic-basin",
    name: "Offshore Deep Pelagic Basin",
    coordinates: [
      [67.0, 20.6],
      [69.0, 20.6],
      [68.8, 18.8],
      [66.8, 18.8],
      [67.0, 20.6],
    ],
    color: {
      sst: "#F97316",
      salinity: "#7C3AED",
      chlorophyll: "#3B82F6",
      anomalies: "#F59E0B",
      trends: "#F59E0B",
    },
    fillOpacity: {
      sst: 0.24,
      salinity: 0.22,
      chlorophyll: 0.24,
      anomalies: 0.24,
      trends: 0.22,
    },
    stroke: {
      sst: "#F97316",
      salinity: "#7C3AED",
      chlorophyll: "#3B82F6",
      anomalies: "#F59E0B",
      trends: "#F59E0B",
    },
    label: {
      sst: "Stratified Basin (29.1°C)",
      salinity: "High Salinity Core (36.4 PSU)",
      chlorophyll: "Oligotrophic Open Sea (0.24 mg/m³)",
      anomalies: "Regional Baseline Offset (+0.9°C)",
      trends: "Basin Scale Trend (+0.15°C/dec)",
    },
  },
];
