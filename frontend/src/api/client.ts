import axios from 'axios';
import type {
  Resume,
  ResumeDetail,
  Tender,
  TenderDetail,
  MatchResponse,
  BatchUploadResult,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 min timeout for large document LLM processing
});

// --- Resumes ---

export async function uploadResume(file: File): Promise<Resume> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post<Resume>('/resumes/upload', form);
  return data;
}

export async function uploadResumesBatch(files: File[]): Promise<BatchUploadResult> {
  const form = new FormData();
  files.forEach((f) => form.append('files', f));
  const { data } = await api.post<BatchUploadResult>('/resumes/upload-batch', form);
  return data;
}

export async function listResumes(): Promise<Resume[]> {
  const { data } = await api.get<Resume[]>('/resumes');
  return data;
}

export async function getResume(id: number): Promise<ResumeDetail> {
  const { data } = await api.get<ResumeDetail>(`/resumes/${id}`);
  return data;
}

export async function deleteResume(id: number): Promise<void> {
  await api.delete(`/resumes/${id}`);
}

// --- Tenders ---

export async function uploadTender(file: File): Promise<Tender> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post<Tender>('/tenders/upload', form);
  return data;
}

export async function listTenders(): Promise<Tender[]> {
  const { data } = await api.get<Tender[]>('/tenders');
  return data;
}

export async function getTender(id: number): Promise<TenderDetail> {
  const { data } = await api.get<TenderDetail>(`/tenders/${id}`);
  return data;
}

export async function deleteTender(id: number): Promise<void> {
  await api.delete(`/tenders/${id}`);
}

// --- Matching ---

export async function runMatching(tenderId: number): Promise<MatchResponse[]> {
  const { data } = await api.post<MatchResponse[]>(`/match/${tenderId}`);
  return data;
}

export async function getMatchResults(tenderId: number): Promise<MatchResponse[]> {
  const { data } = await api.get<MatchResponse[]>(`/match/${tenderId}/results`);
  return data;
}

// --- Chat ---

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  session_id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls: string | null;
  created_at: string;
}

export async function listSessions(): Promise<ChatSession[]> {
  const { data } = await api.get<ChatSession[]>('/chat/sessions');
  return data;
}

export async function createSession(id: string): Promise<ChatSession> {
  const { data } = await api.post<ChatSession>('/chat/sessions', null, { params: { session_id: id } });
  return data;
}

export async function deleteSession(id: string): Promise<void> {
  await api.delete(`/chat/sessions/${id}`);
}

export async function getChatHistory(sessionId: string): Promise<ChatMessage[]> {
  const { data } = await api.get<ChatMessage[]>(`/chat/history/${sessionId}`);
  return data;
}

// --- Smart Upload (SSE) ---

export interface SmartUploadEvent {
  event: 'progress' | 'complete' | 'error';
  step?: string;
  message?: string;
  type?: 'resume' | 'tender';
  // resume fields
  id?: number;
  name?: string;
  skills_count?: number;
  experience_years?: number;
  photo_url?: string | null;
  parse_status?: string;
  // tender fields
  project_name?: string;
  client?: string;
  document_reference?: string | null;
  roles_count?: number;
}

export async function smartUpload(
  file: File,
  onEvent: (event: SmartUploadEvent) => void,
): Promise<void> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch('/api/upload/smart', { method: 'POST', body: form });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Upload failed');
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response stream');
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6)) as SmartUploadEvent;
          onEvent(event);
        } catch {}
      }
    }
  }
}
