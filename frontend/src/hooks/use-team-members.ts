"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

export interface TeamMember {
  user_id: string;
  first_name: string;
  last_name: string;
  is_verified: boolean;
  is_active: boolean;
}

let _cachedTeam: string[] | null = null;
let _cachedTeamFull: TeamMember[] | null = null;

function _fetchTeam(): Promise<TeamMember[]> {
  if (_cachedTeamFull) return Promise.resolve(_cachedTeamFull);
  return api
    .get<TeamMember[]>("/v1/team")
    .then((data) => {
      const active = data.filter((m) => m.is_verified && m.is_active);
      _cachedTeamFull = active;
      _cachedTeam = active.map((m) => m.first_name);
      return active;
    });
}

export function useTeamMembers() {
  const [members, setMembers] = useState<string[]>(_cachedTeam || []);
  useEffect(() => {
    if (_cachedTeam) { setMembers(_cachedTeam); return; }
    _fetchTeam()
      .then(() => setMembers(_cachedTeam || []))
      .catch(() => {});
  }, []);
  return members;
}

export function useTeamMembersFull() {
  const [members, setMembers] = useState<TeamMember[]>(_cachedTeamFull || []);
  useEffect(() => {
    if (_cachedTeamFull) { setMembers(_cachedTeamFull); return; }
    _fetchTeam()
      .then((data) => setMembers(data))
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
