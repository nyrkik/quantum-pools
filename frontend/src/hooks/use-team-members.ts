"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

let _cachedTeam: string[] | null = null;

export function useTeamMembers() {
  const [members, setMembers] = useState<string[]>(_cachedTeam || []);
  useEffect(() => {
    if (_cachedTeam) return;
    api
      .get<
        { first_name: string; is_verified: boolean; is_active: boolean }[]
      >("/v1/team")
      .then((data) => {
        const names = data
          .filter((m) => m.is_verified && m.is_active)
          .map((m) => m.first_name);
        _cachedTeam = names;
        setMembers(names);
      })
      .catch(() => {});
  }, []);
  return members;
}

export const ACTION_TYPES = [
  "follow_up",
  "bid",
  "schedule_change",
  "site_visit",
  "callback",
  "repair",
  "equipment",
  "other",
];
