/** API client for the Resume Matcher backend. */

import axios from "axios";
import type {
  DashboardData,
  JDItem,
  MatchResult,
  ResumeDetail,
  ResumeItem,
} from "./types";

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 120000,
});

// --- Resumes ---

export async function uploadResume(file: File): Promise<ResumeItem> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post("/resumes/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function listResumes(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<{ items: ResumeItem[]; total: number; page: number; page_size: number }> {
  const { data } = await api.get("/resumes/", { params });
  return data;
}

export async function getResume(id: string): Promise<ResumeDetail> {
  const { data } = await api.get(`/resumes/${id}`);
  return data;
}

export async function deleteResume(id: string): Promise<void> {
  await api.delete(`/resumes/${id}`);
}

// --- Jobs ---

export async function createJob(request: {
  title: string;
  department?: string;
  location?: string;
  raw_text: string;
}): Promise<JDItem> {
  const { data } = await api.post("/jobs/", request);
  return data;
}

export async function listJobs(params?: {
  page?: number;
  page_size?: number;
}): Promise<{ items: JDItem[]; total: number; page: number; page_size: number }> {
  const { data } = await api.get("/jobs/", { params });
  return data;
}

export async function getJob(id: string): Promise<JDItem> {
  const { data } = await api.get(`/jobs/${id}`);
  return data;
}

export async function toggleJobActive(id: string): Promise<{ is_active: boolean }> {
  const { data } = await api.put(`/jobs/${id}/toggle-active`);
  return data;
}

export async function deleteJob(id: string): Promise<void> {
  await api.delete(`/jobs/${id}`);
}

// --- Matching ---

export async function matchResume(options: {
  resume_id: string;
  job_id: string;
  enable_llm?: boolean;
}): Promise<MatchResult> {
  const { data } = await api.post("/matching/analyze", {
    resume_id: options.resume_id,
    job_id: options.job_id,
    enable_llm: options.enable_llm ?? true,
  });
  return data;
}

export async function getMatchResult(matchId: string): Promise<MatchResult> {
  const { data } = await api.get(`/matching/results/${matchId}`);
  return data;
}

export async function listMatchResults(params?: {
  resume_id?: string;
  job_id?: string;
}): Promise<{ items: MatchResult[]; total: number }> {
  const { data } = await api.get("/matching/results/", { params });
  return data;
}

export async function deleteMatchResult(id: string): Promise<void> {
  await api.delete(`/matching/results/${id}`);
}

// --- Dashboard ---

export async function getDashboard(): Promise<DashboardData> {
  const { data } = await api.get("/reports/dashboard");
  return data;
}
