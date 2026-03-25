import type { EMDInspection, EMDFacilityListItem, FacilityStatus } from "./emd-types";

export const VIOLATION_LABELS: Record<string, string> = {
  "1a": "Gate Self-Close/Latch",
  "1b": "Gate Hardware",
  "1c": "Emergency Exit Gate",
  "2a": "Pool Enclosure",
  "2b": "Non-Climbable Enclosure",
  "3": "Safety Signs",
  "4": "Safety Equipment",
  "5": "Restrooms/Showers",
  "6": "Hose Bibb Anti-Siphon",
  "7": "Pool Deck",
  "8": "Pool/Deck Lighting",
  "9": "Ladders/Handrails",
  "10a": "Low Chlorine",
  "10b": "High Chlorine",
  "12a": "Low pH",
  "12b": "High pH",
  "13": "High CYA",
  "14": "Test Kit",
  "15": "Records",
  "16": "Water Clarity",
  "17": "Cleanliness",
  "18": "Pool Shell/Tile",
  "19": "Depth Markers",
  "20": "Depth Line",
  "21": "Water Level",
  "22": "Skimmer Assembly",
  "23": "Inlets/Outlets",
  "24": "VGB Suction Covers",
  "25": "Spa Emergency Switch",
  "26": "Spa Temperature",
  "27": "Equipment Room",
  "28": "Safety Vacuum Release",
  "29": "Recirculation System",
  "30": "Equipment/Plumbing",
  "31": "Disinfectant Feeders",
  "32": "Chemical Control System",
  "33": "Turnover Time",
  "34": "Flow Rate",
  "35": "Flow Meters",
  "36": "Pressure/Vacuum Gauges",
  "37": "Electrical Hazards",
  "38": "Filter Maintenance",
  "39": "Wastewater Disposal",
  "43": "EMD Approval Required",
  "44": "Lifeguard Certification",
  "46": "Other",
};

export function getViolationLabel(code: string | null, title: string | null): string {
  if (code) {
    const clean = code.replace(/\.$/, "").trim().toLowerCase();
    if (VIOLATION_LABELS[clean]) return VIOLATION_LABELS[clean];
  }
  return title || "Violation";
}

export function hasClosureViolations(insp: EMDInspection): boolean {
  if (!insp.violations) return false;
  const re = /MAJOR[\s/\-]*(VIOLATION[\s\-]*)?CLOSURE/i;
  return insp.violations.some(v => v.observations && re.test(v.observations));
}

export function getFacilityStatus(inspections: EMDInspection[]): FacilityStatus {
  if (inspections.length === 0) return "compliant";
  const latest = inspections[0];
  if (hasClosureViolations(latest)) return "closure";
  if (latest.reinspection_required) return "reinspection";
  if (latest.total_violations > 0) return "violations";
  return "compliant";
}

export function getListItemStatus(f: EMDFacilityListItem): "green" | "amber" | "red" {
  if (f.total_violations > 10) return "red";
  if (f.total_violations > 0) return "amber";
  return "green";
}

export function getStatusDotColor(status: "green" | "amber" | "red") {
  if (status === "red") return "bg-red-500";
  if (status === "amber") return "bg-amber-500";
  return "bg-green-500";
}

export function getTimelineDotColor(insp: EMDInspection): string {
  if (hasClosureViolations(insp)) return "bg-red-500";
  if (insp.major_violations > 0) return "bg-red-500";
  if (insp.total_violations > 0) return "bg-amber-500";
  return "bg-green-500";
}

/** Clean program identifier: "POOL @ 4407 OAK HOLLOW DR" -> "Pool", "3612 - SPA" -> "Spa" */
export function cleanProgramId(raw: string | null): string {
  if (!raw) return "Pool";
  let clean = raw.replace(/@\s*.*/i, "").replace(/PR\d+/i, "").replace(/\d{4}\s*-\s*/g, "").trim();
  if (!clean) return "Pool";
  return clean.charAt(0).toUpperCase() + clean.slice(1).toLowerCase();
}

export function formatDate(d: string | null): string {
  if (!d) return "--";
  return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
