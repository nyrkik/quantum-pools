export interface TeamMember {
  id: string;
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  role: string;
  job_title: string | null;
  is_developer: boolean;
  is_active: boolean;
  is_verified: boolean;
  last_login: string | null;
  created_at: string;
}

export const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
];

export const ROLES = ["owner", "admin", "manager", "technician", "readonly"];

export const ROLE_LABELS: Record<string, string> = {
  owner: "Full Access",
  admin: "Admin",
  manager: "Standard",
  technician: "Limited",
  readonly: "View Only",
  custom: "Custom",
};

export const ROLE_DESCRIPTIONS: Record<string, string> = {
  owner: "Full access to all features and settings",
  admin: "Manage customers, billing, team. No org settings.",
  manager: "Manage daily operations. No billing or team access.",
  technician: "Own routes, visits, and readings only.",
  readonly: "View-only access across the platform.",
  custom: "Custom permission set assigned by admin.",
};

export const roleBadgeVariant = (role: string) => {
  switch (role) {
    case "owner": return "default" as const;
    case "admin": return "default" as const;
    case "manager": return "secondary" as const;
    case "technician": return "outline" as const;
    default: return "outline" as const;
  }
};
