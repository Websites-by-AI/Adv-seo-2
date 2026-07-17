import type { Audit, Company } from "@/db/schema";

export interface LeadRow extends Company {
  audit: Audit | null;
  proposalId: number | null;
}

export interface Stats {
  total: number;
  checked: number;
  leads: number;
  onFirstPage: number;
  noWebsite: number;
  proposalsReady: number;
  avgScore: number | null;
}

export interface LogEntry {
  id: number;
  level: string;
  message: string;
  createdAt: string;
}

export type FilterKey = "all" | "leads" | "first-page" | "no-site" | "proposals";
