/**
 * API Service – connects the React frontend to the FastAPI backend.
 *
 * Base URL: `VITE_API_URL` (e.g. https://your-api.up.railway.app/api) or,
 * when unset, the relative `/api` path, which the Vite dev server proxies
 * to the local backend (see vite.config.ts).
 *
 * Every request carries an `X-Client-Id` header (a random id stored in
 * localStorage) so each browser only sees its own conversions.
 */

import { getClientId } from '../lib/preferences';

const API_BASE_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/+$/, '');

export interface ConversionHistoryResponse {
  id: string;
  fileName: string;
  date: string;
  status: 'success' | 'failed' | 'processing';
  fileSize: string;
  downloadUrl?: string;
  error?: string;
}

export interface UploadResponse {
  message: string;
  file: ConversionHistoryResponse;
}

export interface StatsResponse {
  total_conversions: number;
  success_count: number;
  failed_count: number;
  processing_count: number;
  today_count: number;
  success_rate: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  max_upload_mb?: number;
  retention_hours?: number;
}

function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('X-Client-Id', getClientId());
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    return detail?.message || fallback;
  } catch {
    return fallback;
  }
}

// ─── Upload ────────────────────────────────────────────────────────────────

export async function uploadPDF(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await apiFetch('/upload', { method: 'POST', body: formData });
  if (!res.ok) {
    throw new Error(await errorMessage(res, 'Upload failed'));
  }
  return res.json();
}

// ─── History ───────────────────────────────────────────────────────────────

export async function fetchHistory(): Promise<ConversionHistoryResponse[]> {
  const res = await apiFetch('/history');
  if (!res.ok) throw new Error('Failed to fetch history');
  return res.json();
}

/** Fetch a single conversion record (used for polling status). */
export async function fetchConversionStatus(fileId: string): Promise<ConversionHistoryResponse> {
  const res = await apiFetch(`/history/${encodeURIComponent(fileId)}`);
  if (!res.ok) throw new Error('Failed to fetch conversion status');
  return res.json();
}

/** Delete a conversion record (the server also deletes its files). */
export async function deleteHistory(fileId: string): Promise<void> {
  const res = await apiFetch(`/history/${encodeURIComponent(fileId)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await errorMessage(res, 'Failed to delete record'));
}

// ─── Download ──────────────────────────────────────────────────────────────

function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/"/g, ''));
    } catch {
      /* fall through */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1] : null;
}

/**
 * Download the converted Excel file. Uses fetch (so the X-Client-Id header is
 * sent) and saves the blob through a temporary object URL.
 */
export async function downloadFile(fileId: string, fallbackName = 'statement.xlsx'): Promise<void> {
  const res = await apiFetch(`/download/${encodeURIComponent(fileId)}`);
  if (!res.ok) throw new Error(await errorMessage(res, 'Download failed'));

  const blob = await res.blob();
  const name = filenameFromDisposition(res.headers.get('Content-Disposition')) || fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ─── Stats ─────────────────────────────────────────────────────────────────

export async function fetchStats(): Promise<StatsResponse> {
  const res = await apiFetch('/stats');
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

// ─── Health ────────────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    const res = await apiFetch('/health');
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

export async function healthCheck(): Promise<boolean> {
  return (await fetchHealth()) !== null;
}
