import { useState, useRef, useEffect } from 'react';
import type { ReactNode } from 'react';
import {
  Send,
  Bot,
  BrainCircuit,
  Terminal,
  ChevronRight,
  ExternalLink,
  Paperclip,
  MoreVertical,
  Users
} from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import { cn } from '../utils/utils';
import { getChatHistory } from '../api/client';

interface ChatMsg {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  thought?: string;
  toolCalls?: { tool: string; input?: any; result?: string; expanded?: boolean }[];
}

interface ParsedMatchCard {
  candidateName: string;
  resumeId?: number;
  roleTitle: string;
  designation?: string;
  experienceYears?: string;
  photoUrl?: string;
  profileUrl?: string;
  fitScore: number;
  structuredScore?: number;
  aiScore?: number;
  explanation?: string;
  strengths: string[];
  breakdown: {
    skills?: number;
    domain?: number;
    edu?: number;
    certs?: number;
    exp?: number;
  };
}

interface ParsedResumeCard {
  candidateName: string;
  resumeId?: number;
  role?: string;
  experience?: string;
  education?: string;
  skills: string[];
  relevance?: string;
  photoUrl?: string;
  profileUrl?: string;
}

interface ParsedResumeCandidateBlock {
  card: ParsedResumeCard;
  role?: string;
  experience?: string;
  educationItems: string[];
  skillsText?: string;
}

interface ParsedTenderCard {
  tenderId: number;
  projectName: string;
  client?: string;
  duration?: string;
  ref?: string;
  date?: string;
  techs: string[];
  rolesCount?: number;
  relevance?: string;
  roles?: string[]; // For detail view
}

interface ParsedChoice {
  label: string;
  value: string;
}

const SHOW_STRUCTURED_RESPONSE_CARDS = true;

function gradeColor(pct: number) {
  if (pct >= 75) return { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' };
  if (pct >= 50) return { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' };
  if (pct >= 25) return { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' };
  return { bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200' };
}

function normalizeCandidateName(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function compactScore(value?: number) {
  if (value === undefined || Number.isNaN(value)) return '0';
  return Number(value).toFixed(0);
}

function parseFields(line: string) {
  const fields: Record<string, string> = {};
  const cleaned = line.replace(/^[-*]\s*/, '').trim();
  const parts = cleaned.split(/\s+\|\s+/);
  for (const part of parts) {
    const idx = part.indexOf(':');
    if (idx === -1) continue;
    const key = part.slice(0, idx).trim().toLowerCase();
    const value = part.slice(idx + 1).trim();
    fields[key] = value;
  }
  return fields;
}

function parseMatchCards(result?: string): ParsedMatchCard[] {
  if (!result || !result.includes('Candidate:') || !result.includes('Fit Score:')) return [];

  return result
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.includes('Candidate:') && line.includes('Fit Score:'))
    .map((line): ParsedMatchCard => {
      const fields = parseFields(line);
      const fitScore = Number((fields['fit score'] || '0').replace('%', ''));
      const strengths = (fields['top strengths'] || '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);

      return {
        candidateName: fields.candidate || 'Unknown Candidate',
        resumeId: fields['resume id'] ? Number(fields['resume id']) : undefined,
        roleTitle: fields.role || 'Candidate Match',
        designation: fields.designation,
        experienceYears: fields.experience,
        photoUrl: fields['photo url'],
        profileUrl: fields['profile url'],
        fitScore,
        structuredScore: fields['structured score'] ? Number(fields['structured score']) : undefined,
        aiScore: fields['ai score'] ? Number(fields['ai score']) : undefined,
        explanation: fields['why best fit'],
        strengths,
        breakdown: {
          skills: fields.skills ? Number(fields.skills) : undefined,
          domain: fields.domain ? Number(fields.domain) : undefined,
          edu: fields.edu ? Number(fields.edu) : undefined,
          certs: fields.certs ? Number(fields.certs) : undefined,
          exp: fields.exp ? Number(fields.exp) : undefined,
        },
      };
    })
    .filter((item) => item.candidateName !== 'Unknown Candidate');
}

function getMatchCardsFromMessage(msg: ChatMsg) {
  const cards: ParsedMatchCard[] = [];
  msg.toolCalls
    ?.filter((tc) => tc.tool === 'get_match_results')
    .forEach((tc) => cards.push(...parseMatchCards(tc.result)));

  if (cards.length === 0) {
    cards.push(...parseMatchCards(msg.content));
  }

  const seen = new Set<string>();
  return cards.filter((card) => {
    const key = `${card.resumeId || card.candidateName}-${card.roleTitle}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function parseResumeCardsFromToolResult(result?: string): ParsedResumeCard[] {
  if (!result) return [];

  return result
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('- ') && line.includes('(ID:') && line.includes(' | '))
    .map((line): ParsedResumeCard | null => {
      const nameMatch = line.match(/^-\s+\*\*(.*?)\*\*\s+\(ID:\s*(\d+)\)\s+\|\s+(.+)$/) || line.match(/^-\s+(.*?)\s+\(ID:\s*(\d+)\)\s+\|\s+(.+)$/);
      if (!nameMatch) return null;

      const [, rawName, rawId, rest] = nameMatch;
      const parts = rest.split(/\s+\|\s+/);
      const fields = parseFields(line);
      const skillsText = fields.skills || '';
      const skills = skillsText
        .split(',')
        .map((skill) => skill.trim())
        .filter(Boolean)
        .slice(0, 8);

      return {
        candidateName: rawName.trim(),
        resumeId: Number(rawId),
        role: fields.role || parts[0]?.replace(/^role:\s*/i, '').trim(),
        experience: fields.experience || parts[1]?.replace(/^experience:\s*/i, '').trim(),
        education: fields.education,
        skills,
        relevance: fields.relevance,
        photoUrl: fields['photo url'] || fields.photo,
        profileUrl: fields['profile url'] || `/resumes/${rawId}`,
      };
    })
    .filter((item): item is ParsedResumeCard => item !== null);
}

function parseResumeCardsFromDetailToolResult(result?: string): ParsedResumeCard[] {
  if (!result) return [];
  const lines = result
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];

  const header = lines[0];
  const headerMatch = header.match(/^\*\*(.*?)\*\*\s+\(ID:\s*(\d+)\)/) || header.match(/^(.*?)\s+\(ID:\s*(\d+)\)/);
  if (!headerMatch) return [];

  const [, rawName, rawId] = headerMatch;
  const card: ParsedResumeCard = {
    candidateName: rawName.trim(),
    resumeId: Number(rawId),
    skills: [],
    profileUrl: `/resumes/${rawId}`,
  };

  for (const line of lines.slice(1)) {
    if (/^role:/i.test(line)) card.role = line.replace(/^role:\s*/i, '').trim();
    if (/^experience:/i.test(line)) card.experience = line.replace(/^experience:\s*/i, '').trim();
    if (/^education:/i.test(line)) card.education = line.replace(/^education:\s*/i, '').trim();
    if (/^skills:/i.test(line)) {
      card.skills = line
        .replace(/^skills:\s*/i, '')
        .split(',')
        .map((skill) => skill.trim())
        .filter(Boolean)
        .slice(0, 8);
    }

    const pipeFields = parseFields(line);
    if (pipeFields['photo url']) card.photoUrl = pipeFields['photo url'];
    if (pipeFields['profile url']) card.profileUrl = pipeFields['profile url'];

    const photoMatch = line.match(/photo url:\s*([^|]+)(?:\s*\||$)/i);
    if (photoMatch?.[1]) card.photoUrl = photoMatch[1].trim();
    const profileMatch = line.match(/profile url:\s*([^|]+)(?:\s*\||$)/i);
    if (profileMatch?.[1]) card.profileUrl = profileMatch[1].trim();
  }

  return [card];
}

function parseResumeCardsFromContent(content?: string): ParsedResumeCard[] {
  if (!content || !content.includes('**')) return [];
  if (content.includes('TND-')) return [];

  const cards: ParsedResumeCard[] = [];
  let current: ParsedResumeCard | null = null;

  for (const line of content.split('\n')) {
    const candidateMatch = line.match(/^\s*(?:[-*]\s+)?\*\*(.+?)\*\*(?:\s*\(ID:\s*(\d+)\))?\s*$/);
    if (candidateMatch) {
      current = {
        candidateName: candidateMatch[1].trim(),
        resumeId: candidateMatch[2] ? Number(candidateMatch[2]) : undefined,
        skills: [],
      };
      cards.push(current);
      continue;
    }

    if (!current) continue;

    const fieldMatch = line.match(/^\s*[-*]?\s*\*?\*?(Role|Experience|Education|Skills|Photo URL|Profile URL)\*?\*?:\s*(.+)$/i);
    if (!fieldMatch) continue;

    const key = fieldMatch[1].toLowerCase();
    const value = fieldMatch[2].trim();
    if (key === 'role') current.role = value;
    if (key === 'experience') current.experience = value;
    if (key === 'education') current.education = value;
    if (key === 'photo url') current.photoUrl = value;
    if (key === 'profile url') current.profileUrl = value;
    if (key === 'skills') {
      current.skills = value
        .split(',')
        .map((skill) => skill.trim())
        .filter(Boolean)
        .slice(0, 8);
    }
  }

  return cards;
}

function getResumeCardsFromMessage(msg: ChatMsg) {
  const cards: ParsedResumeCard[] = [];
  msg.toolCalls
    ?.forEach((tc) => {
      if (tc.tool === 'sql_query_resumes' || tc.tool === 'search_resumes' || tc.tool === 'query_resumes_dynamic' || tc.tool === 'get_resume_inventory') {
        cards.push(...parseResumeCardsFromToolResult(tc.result));
      }
      if (tc.tool === 'get_resume_detail') {
        cards.push(...parseResumeCardsFromDetailToolResult(tc.result));
      }
    });

  if (cards.length === 0) {
    cards.push(...parseResumeCardsFromContent(msg.content));
  }

  const seen = new Set<string>();
  return cards.filter((card) => {
    const key = `${card.resumeId || normalizeCandidateName(card.candidateName)}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function findResumeCardForLine(line: string, cards: ParsedResumeCard[]) {
  const normalizedLine = normalizeCandidateName(line);
  return cards.find((card) => {
    const normalizedName = normalizeCandidateName(card.candidateName);
    return normalizedName && normalizedLine.includes(normalizedName);
  });
}

function sanitizeResumeAnswerContent(content: string) {
  return content
    .split('\n')
    .filter((line) => !/^\s*[-*]\s+\!\[.*?\]\(.*?\)\s*$/i.test(line))
    .filter((line) => !/^\s*[-*]?\s*\*?\*?(photo|photo url|profile|profile url)\*?\*?:/i.test(line))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function cleanResumeSectionTitle(line: string) {
  return line
    .replace(/^#{1,6}\s*/, '')
    .replace(/^\*\*/, '')
    .replace(/\*\*:?$/, '')
    .replace(/:$/, '')
    .trim();
}

function isResumeSectionHeading(line: string) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('- ') || trimmed.startsWith('* ')) return false;
  if (!trimmed.endsWith(':')) return false;

  const title = cleanResumeSectionTitle(trimmed).toLowerCase();
  return [
    'contact information',
    'contact details',
    'skills',
    'technical skills',
    'core skills',
    'experience',
    'professional experience',
    'education',
    'projects',
    'certifications',
    'summary',
    'profile summary',
    'achievements'
  ].includes(title);
}

function parseResumeSections(content: string) {
  const lines = content.split('\n');
  const intro: string[] = [];
  const sections: { title: string; items: string[] }[] = [];
  let currentSection: { title: string; items: string[] } | null = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    if (isResumeSectionHeading(line)) {
      currentSection = { title: cleanResumeSectionTitle(line), items: [] };
      sections.push(currentSection);
      continue;
    }

    if (currentSection) {
      currentSection.items.push(line.replace(/^[-*]\s+/, '').trim());
    } else {
      intro.push(line);
    }
  }

  return { intro: intro.join('\n').trim(), sections };
}

function findResumeCardByHeader(line: string, cards: ParsedResumeCard[]) {
  const idMatch = line.match(/\(ID:\s*(\d+)\)/i);
  if (idMatch) {
    const resumeId = Number(idMatch[1]);
    const byId = cards.find((card) => card.resumeId === resumeId);
    if (byId) return byId;
  }

  const candidateMatch = line.match(/^\s*(?:[-*]\s+)?\*\*(.+?)\*\*(?:\s*\(ID:\s*(\d+)\))?\s*$/);
  const candidateName = candidateMatch?.[1]?.trim();
  if (!candidateName) return undefined;

  const normalizedName = normalizeCandidateName(candidateName);
  return cards.find((card) => normalizeCandidateName(card.candidateName) === normalizedName);
}

function parseResumeCandidateBlocks(content: string, cards: ParsedResumeCard[]) {
  const lines = content.split('\n');
  const introLines: string[] = [];
  const outroLines: string[] = [];
  const candidates: ParsedResumeCandidateBlock[] = [];
  let current: ParsedResumeCandidateBlock | null = null;
  let inEducation = false;
  let sawCandidate = false;

  const flushCurrent = () => {
    if (!current) return;
    candidates.push(current);
    current = null;
    inEducation = false;
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) continue;

    const candidateMatch = trimmed.match(/^\s*(?:[-*]\s+)?\*\*(.+?)\*\*(?:\s*\(ID:\s*(\d+)\))?\s*$/);
    if (candidateMatch) {
      flushCurrent();
      sawCandidate = true;

      const existingCard = findResumeCardByHeader(trimmed, cards);
      current = {
        card: existingCard || {
          candidateName: candidateMatch[1].trim(),
          resumeId: candidateMatch[2] ? Number(candidateMatch[2]) : undefined,
          skills: [],
        },
        role: existingCard?.role,
        experience: existingCard?.experience,
        educationItems: [],
        skillsText: existingCard?.skills?.join(', ') || undefined,
      };
      continue;
    }

    if (!sawCandidate) {
      introLines.push(trimmed);
      continue;
    }

    if (!current) {
      outroLines.push(trimmed);
      continue;
    }

    if (/^there are \d+ more candidates/i.test(trimmed) || /^all .* are already shown/i.test(trimmed)) {
      flushCurrent();
      outroLines.push(trimmed);
      continue;
    }

    if (/^-\s*role:/i.test(trimmed)) {
      current.role = trimmed.replace(/^-\s*role:\s*/i, '').trim();
      inEducation = false;
      continue;
    }

    if (/^-\s*experience:/i.test(trimmed)) {
      current.experience = trimmed.replace(/^-\s*experience:\s*/i, '').trim();
      inEducation = false;
      continue;
    }

    if (/^-\s*education:\s*$/i.test(trimmed)) {
      inEducation = true;
      continue;
    }

    const educationInlineMatch = trimmed.match(/^-\s*education:\s*(.+)$/i);
    if (educationInlineMatch) {
      const value = educationInlineMatch[1].trim();
      current.educationItems = value && value !== 'N/A' ? [value] : [];
      inEducation = false;
      continue;
    }

    if (inEducation && /^-\s+/.test(trimmed)) {
      current.educationItems.push(trimmed.replace(/^-\s+/, '').trim());
      continue;
    }

    if (/^-\s*skills:/i.test(trimmed)) {
      current.skillsText = trimmed.replace(/^-\s*skills:\s*/i, '').trim();
      inEducation = false;
      continue;
    }

    if (/^-\s*(photo url|profile url):/i.test(trimmed)) {
      continue;
    }

    if (inEducation) {
      inEducation = false;
    }
  }

  flushCurrent();

  return {
    intro: introLines.join('\n').trim(),
    candidates,
    outro: outroLines.join('\n').trim(),
  };
}

function ResumeInlineAnswer({ content, cards }: { content: string; cards: ParsedResumeCard[] }) {
  const sanitizedContent = sanitizeResumeAnswerContent(content);
  const { intro, sections } = parseResumeSections(sanitizedContent);
  const primaryCard = cards[0];
  const detailView = cards.length === 1 && sections.length > 0;

  if (detailView && primaryCard) {
    return (
      <div className="space-y-5">
        {intro && (
          <div className="prose prose-slate prose-sm max-w-none text-[15px] leading-relaxed">
            <MarkdownRenderer content={intro} />
          </div>
        )}

        <div className="ai-inline-person not-prose rounded-[1.75rem] border border-slate-200/80 bg-white/90 p-5 shadow-[0_24px_50px_-28px_rgba(15,23,42,0.45)] backdrop-blur-sm">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-violet-100 bg-violet-50 shadow-sm shrink-0">
              {primaryCard.photoUrl ? (
                <img src={primaryCard.photoUrl} alt="" className="h-full w-full rounded-2xl object-cover" />
              ) : (
                <Users className="w-5 h-5 text-violet-500" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[20px] font-black tracking-tight text-slate-900">{primaryCard.candidateName}</h3>
                {primaryCard.resumeId && (
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                    ID {primaryCard.resumeId}
                  </span>
                )}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <span className="rounded-full bg-violet-50 px-3 py-1 text-[11px] font-bold text-violet-700 border border-violet-100">
                  {primaryCard.role || 'Personnel Profile'}
                </span>
                {primaryCard.experience && (
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600 border border-slate-200">
                    {primaryCard.experience}
                  </span>
                )}
                {primaryCard.education && (
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600 border border-slate-200">
                    {primaryCard.education}
                  </span>
                )}
              </div>
            </div>
            {(primaryCard.profileUrl || primaryCard.resumeId) && (
              <Link
                to={primaryCard.profileUrl || `/resumes/${primaryCard.resumeId}`}
                className="inline-flex items-center gap-1.5 rounded-xl border border-violet-100 bg-violet-50 px-3 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-violet-600 transition-all hover:bg-violet-600 hover:text-white shrink-0"
              >
                Open Resume <ExternalLink className="w-3 h-3" />
              </Link>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4">
          {sections.map((section, index) => (
            <section
              key={`${section.title}-${index}`}
              className="not-prose rounded-[1.5rem] border border-slate-200/80 bg-white/88 p-5 shadow-[0_18px_38px_-28px_rgba(15,23,42,0.45)] backdrop-blur-sm"
            >
              <div className="mb-4 flex items-center gap-3">
                <div className="h-2.5 w-2.5 rounded-full bg-violet-500 shadow-[0_0_12px_rgba(139,92,246,0.45)]" />
                <h4 className="text-[15px] font-black tracking-tight text-slate-900">{section.title}</h4>
              </div>
              <div className="space-y-2">
                {section.items.map((item, itemIndex) => (
                  <div
                    key={`${section.title}-${itemIndex}`}
                    className="rounded-2xl border border-slate-100 bg-slate-50/80 px-4 py-3 text-[14px] font-medium leading-relaxed text-slate-700"
                  >
                    {item}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    );
  }

  const candidateBlocks = parseResumeCandidateBlocks(sanitizedContent, cards);
  if (candidateBlocks.candidates.length > 0) {
    return (
      <div className="space-y-5">
        {candidateBlocks.intro && (
          <div className="prose prose-slate prose-sm max-w-none text-[15px] leading-relaxed">
            <MarkdownRenderer content={candidateBlocks.intro} />
          </div>
        )}

        <div className="space-y-6">
          {candidateBlocks.candidates.map((block, index) => {
            const card = block.card;
            const profileUrl = card.profileUrl || (card.resumeId ? `/resumes/${card.resumeId}` : undefined);
            const skillsText = block.skillsText || (card.skills.length > 0 ? card.skills.join(', ') : 'N/A');

            return (
              <div key={`${card.resumeId || card.candidateName}-${index}`} className="space-y-3">
                <div className="ai-inline-person not-prose flex items-center gap-3 rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 shadow-sm animate-in fade-in slide-in-from-left-2 duration-500">
                  <div className="w-2 h-2 rounded-full bg-violet-500 shrink-0" />
                  <div className="w-11 h-11 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center overflow-hidden shrink-0 shadow-sm">
                    {card.photoUrl ? (
                      <img src={card.photoUrl} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <Users className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[15px] font-black text-slate-900 tracking-tight">{card.candidateName}</span>
                      {card.resumeId && (
                        <span className="text-[12px] font-semibold text-slate-500">(ID: {card.resumeId})</span>
                      )}
                    </div>
                    <div className="mt-1 text-[11px] font-semibold text-slate-500">
                      {block.role || card.role || 'Personnel Profile'}
                      {(block.experience || card.experience) ? ` | ${block.experience || card.experience}` : ''}
                    </div>
                  </div>
                  {profileUrl && (
                    <Link
                      to={profileUrl}
                      className="inline-flex items-center gap-1.5 text-[9px] text-violet-600 font-black hover:bg-violet-600 hover:text-white transition-all bg-violet-50 px-3 py-2 rounded-xl border border-violet-100 uppercase tracking-wider shadow-sm shrink-0"
                    >
                      Profile <ExternalLink className="w-2.5 h-2.5" />
                    </Link>
                  )}
                </div>

                <ul className="not-prose space-y-2 pl-6 text-[15px] leading-relaxed text-slate-100/95">
                  <li className="flex items-start gap-3">
                    <span className="mt-2 h-2 w-2 rounded-full bg-violet-500 shrink-0" />
                    <span><strong className="text-white">Role:</strong> {block.role || card.role || 'N/A'}</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="mt-2 h-2 w-2 rounded-full bg-violet-500 shrink-0" />
                    <span><strong className="text-white">Experience:</strong> {block.experience || card.experience || 'N/A'}</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="mt-2 h-2 w-2 rounded-full bg-violet-500 shrink-0" />
                    <div className="space-y-1">
                      <span><strong className="text-white">Education:</strong></span>
                      {block.educationItems.length > 0 ? (
                        <ul className="space-y-1 pl-5">
                          {block.educationItems.map((item, itemIndex) => (
                            <li key={`${card.resumeId || card.candidateName}-edu-${itemIndex}`} className="list-disc marker:text-violet-400">
                              {item}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <div>N/A</div>
                      )}
                    </div>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="mt-2 h-2 w-2 rounded-full bg-violet-500 shrink-0" />
                    <span><strong className="text-white">Skills:</strong> {skillsText}</span>
                  </li>
                </ul>
              </div>
            );
          })}
        </div>

        {candidateBlocks.outro && (
          <div className="prose prose-slate prose-sm max-w-none text-[15px] leading-relaxed">
            <MarkdownRenderer content={candidateBlocks.outro} />
          </div>
        )}
      </div>
    );
  }

  const lines = sanitizedContent.split('\n');
  const blocks: ReactNode[] = [];
  let buffer: string[] = [];
  let candidateCount = 0;

  const flushBuffer = () => {
    const chunk = buffer.join('\n').trim();
    if (chunk) {
      blocks.push(
        <div key={`chunk-${blocks.length}`} className="prose prose-slate prose-sm max-w-none text-[15px] leading-relaxed">
          <MarkdownRenderer content={chunk} />
        </div>
      );
    }
    buffer = [];
  };

  for (const line of lines) {
    const matchedCard = findResumeCardForLine(line, cards);
    if (!matchedCard) {
      buffer.push(line);
      continue;
    }

    flushBuffer();
    candidateCount += 1;

    const idMatch = line.match(/\(ID:\s*(\d+)\)/i);
    blocks.push(
      <div
        key={`candidate-${candidateCount}-${matchedCard.resumeId || matchedCard.candidateName}`}
        className="ai-inline-person not-prose flex items-center gap-3 rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 shadow-sm animate-in fade-in slide-in-from-left-2 duration-500"
        style={{ animationDelay: `${candidateCount * 80}ms` }}
      >
        <div className="w-2 h-2 rounded-full bg-violet-500 shrink-0" />
        <div className="w-11 h-11 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center overflow-hidden shrink-0 shadow-sm">
          {matchedCard.photoUrl ? (
            <img src={matchedCard.photoUrl} alt="" className="w-full h-full object-cover" />
          ) : (
            <Users className="w-4 h-4 text-slate-400" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[15px] font-black text-slate-900 tracking-tight">{matchedCard.candidateName}</span>
            {idMatch?.[1] && (
              <span className="text-[12px] font-semibold text-slate-500">(ID: {idMatch[1]})</span>
            )}
          </div>
          <div className="mt-1 text-[11px] font-semibold text-slate-500">
            {matchedCard.role || 'Personnel Profile'}
            {matchedCard.experience ? ` | ${matchedCard.experience}` : ''}
          </div>
        </div>
        {(matchedCard.profileUrl || matchedCard.resumeId) && (
          <Link
            to={matchedCard.profileUrl || `/resumes/${matchedCard.resumeId}`}
            className="inline-flex items-center gap-1.5 text-[9px] text-violet-600 font-black hover:bg-violet-600 hover:text-white transition-all bg-violet-50 px-3 py-2 rounded-xl border border-violet-100 uppercase tracking-wider shadow-sm shrink-0"
          >
            Profile <ExternalLink className="w-2.5 h-2.5" />
          </Link>
        )}
      </div>
    );
  }

  flushBuffer();

  return <div className="space-y-3">{blocks}</div>;
}

function parseTenderCardsFromToolResult(result?: string): ParsedTenderCard[] {
  if (!result) return [];

  const cards: ParsedTenderCard[] = [];
  const lines = result.split('\n').map(l => l.trim());

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // List view match: - **TND-0004** | Project Name | Client | X roles | Tech: ... | Relevance: ...
    const listMatch = line.match(/^\s*[-*]\s+\*\*TND-(\d+)\*\*\s+\|\s+(.+?)\s+\|\s+(.+?)\s+\|\s+(\d+)\s+roles\s+\|\s+Tech:\s+(.*?)(?:\s+\|\s+Relevance:\s+(.*))?$/);
    if (listMatch) {
      const [, id, name, client, roles, techs, rel] = listMatch;
      cards.push({
        tenderId: Number(id),
        projectName: name.trim(),
        client: client.trim(),
        rolesCount: Number(roles),
        techs: techs.split(',').map(t => t.trim()).filter(Boolean),
        relevance: rel?.trim(),
      });
      continue;
    }

    // Detail view match
    const detailHeader = line.match(/^\*\*TND-(\d+)\*\*\s+\|\s+(.+)$/);
    if (detailHeader) {
      const tenderId = Number(detailHeader[1]);
      const projectName = detailHeader[2].trim();
      let client = "N/A";
      let duration = "N/A";
      let ref = "N/A";
      let date = "N/A";
      let techs: string[] = [];
      let roles: string[] = [];
      let rolesCount: number | undefined;

      // Parse next few lines for details
      let j = i + 1;
      let inRequiredRoles = false;
      while (j < lines.length && j < i + 14) {
        const nextLine = lines[j];
        const normalizedLine = nextLine.replace(/^-\s+/, '');

        if (normalizedLine.includes('Client:')) {
          const cm = normalizedLine.match(/Client:\s+(.+?)(?:\s+\||\s*$)/);
          if (cm) client = cm[1].trim();
          const dm = normalizedLine.match(/Duration:\s+(.+?)(?:\s+\||\s*$)/);
          if (dm) duration = dm[1].trim();
        }
        if (normalizedLine.includes('Ref:') || normalizedLine.includes('Reference:')) {
          const rm = normalizedLine.match(/(?:Ref|Reference):\s+(.+?)(?:\s+\||\s*$)/);
          if (rm) ref = rm[1].trim();
          const dtm = normalizedLine.match(/Date:\s+(.+?)(?:\s+\||\s*$)/);
          if (dtm) date = dtm[1].trim();
        }
        if (normalizedLine.includes('Technologies:')) {
          techs = normalizedLine.replace(/Technologies:\s+/, '').split(',').map(t => t.trim()).filter(Boolean);
        }
        if (normalizedLine.startsWith('Roles (')) {
          const countMatch = normalizedLine.match(/Roles\s+\((\d+)\)/i);
          if (countMatch) rolesCount = Number(countMatch[1]);
          inRequiredRoles = true;
        } else if (normalizedLine.startsWith('Roles Count:')) {
          const countMatch = normalizedLine.match(/Roles Count:\s+(\d+)/i);
          if (countMatch) rolesCount = Number(countMatch[1]);
        } else if (normalizedLine.startsWith('Required Roles:')) {
          inRequiredRoles = true;
        } else if (inRequiredRoles && nextLine.startsWith('- ')) {
          roles.push(normalizedLine);
        }

        if (lines[j + 1]?.startsWith('**TND-')) break; // Next tender start
        j++;
      }

      cards.push({
        tenderId,
        projectName,
        client,
        duration,
        ref,
        date,
        techs,
        rolesCount,
        roles
      });
      i = j; // Advance outer loop
    }
  }

  return cards;
}

function getTenderCardsFromMessage(msg: ChatMsg) {
  const cards: ParsedTenderCard[] = [];
  msg.toolCalls
    ?.filter((tc) => tc.tool === 'search_tenders' || tc.tool === 'get_tender_detail')
    .forEach((tc) => cards.push(...parseTenderCardsFromToolResult(tc.result)));

  return cards;
}

function MiniBadge({ label, value, max }: { label: string; value?: number; max: number }) {
  const pct = max > 0 ? ((value || 0) / max) * 100 : 0;
  const color = gradeColor(pct);
  return (
    <div className={`flex flex-col gap-1 p-2 rounded-xl border ${color.border} ${color.bg} min-w-[70px]`}>
      <span className="text-[8px] font-black uppercase tracking-widest text-slate-400">{label}</span>
      <div className="flex items-baseline gap-0.5">
        <span className={`text-sm font-black ${color.text}`}>{compactScore(value)}</span>
        <span className="text-[8px] font-medium text-slate-400 opacity-50">/{max}</span>
      </div>
    </div>
  );
}

function ChatMatchRow({ item, rank }: { item: ParsedMatchCard; rank: number }) {
  return (
    <div className="group relative bg-white border border-slate-200 rounded-[1.5rem] p-5 transition-all hover:border-violet-200 hover:shadow-xl hover:shadow-slate-200/50 overflow-hidden">
      <div className="flex items-start gap-5">
        <div className="w-10 h-10 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center shrink-0">
          <span className="text-xs font-black text-slate-900">{rank}</span>
        </div>

        {item.photoUrl ? (
          <img src={item.photoUrl} alt="" className="w-12 h-12 rounded-xl object-cover border border-slate-200 shrink-0" />
        ) : (
          <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center shrink-0">
            <span className="text-lg opacity-40">👤</span>
          </div>
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <h3 className="text-sm font-black text-slate-900 truncate uppercase tracking-tight">{item.candidateName}</h3>
            {(item.profileUrl || item.resumeId) && (
              <Link
                to={item.profileUrl || `/resumes/${item.resumeId}`}
                className="flex items-center gap-1.5 text-[10px] text-violet-600 font-bold hover:text-white hover:bg-violet-600 transition-all bg-violet-50 px-2.5 py-1 rounded-lg border border-violet-100 uppercase tracking-wider"
              >
                Open Resume <ExternalLink className="w-2.5 h-2.5" />
              </Link>
            )}
          </div>
          <p className="text-[11px] font-bold text-slate-400 mb-4 truncate italic">
            {item.roleTitle} — {item.experienceYears}
          </p>

          <div className="flex flex-wrap gap-2">
            <MiniBadge label="Skills" value={item.breakdown.skills} max={35} />
            <MiniBadge label="Domain" value={item.breakdown.domain} max={25} />
            <MiniBadge label="Edu" value={item.breakdown.edu} max={15} />
            <MiniBadge label="Certs" value={item.breakdown.certs} max={15} />
            <MiniBadge label="Exp" value={item.breakdown.exp} max={10} />
          </div>
        </div>

        <div className="text-right">
          <div className="text-2xl font-black text-slate-900 tracking-tighter leading-none">{item.fitScore}%</div>
          <div className="text-[9px] font-black text-slate-300 uppercase tracking-widest mt-1">Match Index</div>
        </div>
      </div>
    </div>
  );
}

function ChatMatchCards({ cards }: { cards: ParsedMatchCard[] }) {
  if (cards.length === 0) return null;
  const topScore = cards[0].fitScore;
  const topColor = gradeColor(topScore);

  return (
    <div className="w-full space-y-4">
      <div className="bg-white border border-slate-200 rounded-[2.5rem] overflow-hidden shadow-xl shadow-slate-200/50">
        <div className="flex items-center justify-between px-8 py-6 border-b border-slate-100 bg-slate-50/50">
          <div>
            <h3 className="text-sm font-black text-slate-900 uppercase tracking-tight leading-none">Strategic Match Results</h3>
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-2 px-1">
              {cards.length} candidate{cards.length === 1 ? '' : 's'} identified
            </p>
          </div>
          <div className="text-right">
            <div className={`text-2xl font-black ${topColor.text}`}>{topScore.toFixed(0)}%</div>
            <div className="text-[9px] font-black text-slate-300 uppercase tracking-widest">Top Match Index</div>
          </div>
        </div>
        <div className="p-4 space-y-3 bg-white">
          {cards.map((item, idx) => (
            <ChatMatchRow key={`${item.resumeId || item.candidateName}-${item.roleTitle}`} item={item} rank={idx + 1} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ThinkingIndicator({ message }: { message?: string }) {
  return (
    <div className="flex justify-start animate-in fade-in slide-in-from-left-4 duration-500 pl-12 relative items-center gap-4">
      <div className="absolute left-0 top-0 w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-violet-500 shadow-sm animate-pulse-soft">
        <BrainCircuit className="w-4 h-4" />
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1.5 text-slate-400">
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-dot-bounce [animation-delay:-0.3s]" />
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-dot-bounce [animation-delay:-0.15s]" />
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-dot-bounce" />
          </div>
          <span className="text-[10px] font-black uppercase tracking-[0.2em]">{message || 'Processing Intelligence'}</span>
        </div>
        <div className="h-2 w-48 bg-slate-100 rounded-full overflow-hidden relative">
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-violet-200 to-transparent w-full animate-shimmer" style={{ backgroundSize: '200% 100%' }} />
        </div>
      </div>
    </div>
  );
}

function ChatTenderCards({ cards }: { cards: ParsedTenderCard[] }) {
  if (cards.length === 0) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
      {cards.map((item, idx) => (
        <div key={idx} className="group relative bg-white border border-slate-200 rounded-3xl p-5 transition-all hover:border-violet-200 hover:shadow-xl hover:shadow-slate-200/40 flex flex-col gap-4 overflow-hidden animate-in slide-in-from-bottom-4 duration-500" style={{ animationDelay: `${idx * 100}ms` }}>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-400 group-hover:bg-violet-50 group-hover:border-violet-100 group-hover:text-violet-600 transition-colors shrink-0">
                <BrainCircuit className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-black text-slate-900 uppercase tracking-tight leading-none mb-1 truncate max-w-[200px]">{item.projectName}</h3>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">TND-{String(item.tenderId).padStart(4, '0')}</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="p-3 bg-slate-50/50 rounded-2xl border border-slate-100/50">
              <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Client</span>
              <p className="text-[11px] font-bold text-slate-600 truncate">{item.client || 'N/A'}</p>
            </div>
            <div className="p-3 bg-slate-50/50 rounded-2xl border border-slate-100/50">
              <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Scale</span>
              <p className="text-[11px] font-bold text-slate-600 truncate">{item.rolesCount ? `${item.rolesCount} Roles` : item.duration || 'N/A'}</p>
            </div>
          </div>

          {(item.ref || item.date || item.duration) && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <div className="p-3 bg-slate-50/40 rounded-2xl border border-slate-100/50">
                <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Duration</span>
                <p className="text-[11px] font-bold text-slate-600 truncate">{item.duration || 'N/A'}</p>
              </div>
              <div className="p-3 bg-slate-50/40 rounded-2xl border border-slate-100/50">
                <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Reference</span>
                <p className="text-[11px] font-bold text-slate-600 truncate">{item.ref || 'N/A'}</p>
              </div>
              <div className="p-3 bg-slate-50/40 rounded-2xl border border-slate-100/50">
                <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Date</span>
                <p className="text-[11px] font-bold text-slate-600 truncate">{item.date || 'N/A'}</p>
              </div>
            </div>
          )}

          {item.techs.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {item.techs.map((tech, ti) => (
                <span key={ti} className="px-2.5 py-1 rounded-lg bg-white border border-slate-100 text-[9px] font-bold text-slate-500 shadow-sm group-hover:border-violet-100 group-hover:text-violet-700 transition-all">
                  {tech}
                </span>
              ))}
            </div>
          )}

          {item.roles && item.roles.length > 0 && (
            <div className="space-y-1 mt-1 border-t border-slate-50 pt-3">
              <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-2">Technical Roles</span>
              {item.roles.slice(0, 3).map((role, ri) => (
                <p key={ri} className="text-[10px] font-bold text-slate-500 flex items-center gap-2">
                  <div className="w-1 h-1 rounded-full bg-violet-300" />
                  {role}
                </p>
              ))}
              {item.roles.length > 3 && (
                <p className="text-[9px] font-bold text-violet-400 pl-3">+{item.roles.length - 3} more specialization areas</p>
              )}
            </div>
          )}

          {item.relevance && (
            <div className="mt-auto pt-4 border-t border-slate-50 flex items-center justify-between">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Match Relevance</span>
              <span className="text-[11px] text-violet-600 font-black uppercase tracking-tight bg-violet-50 px-2 py-1 rounded-lg">{item.relevance}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ChatChoices({ question, choices, onSelect, disabled }: { question?: string; choices: ParsedChoice[]; onSelect: (label: string, value: string) => void; disabled?: boolean }) {
  if (choices.length === 0) return null;

  return (
    <div className="w-full animate-in slide-in-from-bottom-4 fade-in duration-500 relative z-30 px-4 md:px-0">
      <div className="w-full bg-white border-x border-t border-slate-200 rounded-t-[2.5rem] shadow-[0_-20px_50px_-15px_rgba(0,0,0,0.05)] overflow-hidden">
        <div className="flex items-center gap-3 px-8 py-5 border-b border-slate-100 bg-slate-50/50">
          <div className="w-8 h-8 rounded-xl bg-violet-600 flex items-center justify-center shadow-lg shadow-violet-200/50">
            <BrainCircuit className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1">
            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-0.5 leading-none">Decision Console</h4>
            <p className="text-[13px] font-black text-slate-900 leading-tight">{question || 'Input Required'}</p>
          </div>
          <span className="text-[9px] font-black text-violet-600 bg-violet-50 px-3 py-1.5 rounded-full uppercase tracking-widest border border-violet-100 animate-pulse">Action Required</span>
        </div>
        <div className="p-4 bg-white/50">
          <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto custom-scrollbar pr-1">
            {choices.map((choice, i) => (
              <button
                key={i}
                onClick={() => !disabled && onSelect(choice.label, choice.value)}
                disabled={disabled}
                className="group flex items-center gap-4 w-full px-5 py-4 bg-white hover:bg-violet-600 border border-slate-200 hover:border-violet-600 rounded-2xl transition-all shadow-sm active:scale-[0.98] disabled:opacity-50"
              >
                <div className="w-7 h-7 rounded-lg bg-slate-50 text-slate-400 flex items-center justify-center text-[10px] font-black group-hover:bg-white/20 group-hover:text-white transition-colors shrink-0">
                  {i + 1}
                </div>
                <div className="flex-1 text-left">
                  <p className="text-[12px] font-black text-slate-700 group-hover:text-white transition-colors leading-tight">
                    {choice.label}
                  </p>
                </div>
                <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-white transition-colors" />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function RenderToolResult({ result }: { result: string }) {
  try {
    const parsed = JSON.parse(result);
    return <pre className="text-[11px] font-mono whitespace-pre text-neutral-400">{JSON.stringify(parsed, null, 2)}</pre>;
  } catch {
    return <MarkdownRenderer content={result} />;
  }
}

// Helper: format scores and grades

export default function Chat() {
  const { sessionId: routeSessionId } = useParams();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [pendingChoices, setPendingChoices] = useState<ParsedChoice[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState('');

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 1. Session ID Management
  const sessionId = routeSessionId;

  // 2. Redirect to new session if none provided
  useEffect(() => {
    if (!sessionId && !location.pathname.includes('matching')) {
      const newId = crypto.randomUUID();
      navigate(`/chat/${newId}`, { replace: true });
    }
  }, [sessionId, navigate]);

  // 3. Fetch history when sessionId changes
  useEffect(() => {
    if (sessionId) {
      loadHistory();
    }
  }, [sessionId]);

  const loadHistory = async () => {
    if (!sessionId) return;
    try {
      const history = await getChatHistory(sessionId);
      const formatted: ChatMsg[] = history.map(m => ({
        role: m.role as any,
        content: m.content,
        toolCalls: m.tool_calls
          ? JSON.parse(m.tool_calls).map((tc: any) => ({
              tool: tc.tool,
              input: tc.input,
              result: tc.result ?? tc.output,
              expanded: false,
            }))
          : undefined
      }));
      setMessages(formatted);
    } catch (error) {
      console.error('Failed to load chat history:', error);
      setMessages([]);
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({
      top: container.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages, loading]);

  const toggleToolLog = (msgIdx: number, toolIdx: number) => {
    setMessages(prev => {
      const copy = [...prev];
      const msg = { ...copy[msgIdx] };
      if (msg.toolCalls) {
        const toolCalls = [...msg.toolCalls];
        toolCalls[toolIdx] = { ...toolCalls[toolIdx], expanded: !toolCalls[toolIdx].expanded };
        msg.toolCalls = toolCalls;
        copy[msgIdx] = msg;
      }
      return copy;
    });
  };

  const handleChoiceSelect = (label: string, value: string) => {
    const displayMsg = `I've selected: ${label}`;
    const technicalMsg = value;

    setMessages(prev => [
      ...prev,
      { role: 'user', content: displayMsg }
    ]);

    setPendingChoices([]);
    setPendingQuestion('');
    sendMessage(technicalMsg);
  };

  const handleSend = () => {
    if (!input.trim() || loading || !sessionId) return;
    const msg: ChatMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, msg]);
    setInput('');
    sendMessage(input);
  };

  const sendMessage = async (messageText: string) => {
    setLoading(true);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageText,
          session_id: sessionId
        }),
      });

      const reader = response.body?.getReader();
      if (!reader) return;

      let currentMsg: ChatMsg = { role: 'assistant', content: '' };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = new TextDecoder().decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.event === 'thought') {
              setLoadingStep('Synthesizing Knowledge');
              currentMsg.thought = (currentMsg.thought || '') + (data.content || data.token || data.message || '');
            } else if (data.event === 'answer') {
              setLoadingStep('Finalizing Response');
              currentMsg.content += data.content;
              const content = currentMsg.content;
              const choiceRegex = /\[\[CHOICE:\s*(.*?)\s*\|\s*(.*?)\s*\]\]/g;
              const choices: ParsedChoice[] = [];
              let match;
              while ((match = choiceRegex.exec(content)) !== null) {
                choices.push({ label: match[1], value: match[2] });
              }

              if (choices.length > 0) {
                setPendingChoices(choices);
                const rawQuestion = content.split('[[CHOICE:')[0].trim();
                const cleanQuestion = rawQuestion.replace(/\s+\d+\.?\s*$/, '').trim();
                setPendingQuestion(cleanQuestion);
              } else {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (last?.role === 'assistant') {
                    return [...prev.slice(0, -1), { ...currentMsg }];
                  }
                  return [...prev, { ...currentMsg }];
                });
              }
            } else if (data.event === 'tool_call') {
              setLoadingStep(`Running ${data.tool.replace(/_/g, ' ')}`);
              if (!currentMsg.toolCalls) currentMsg.toolCalls = [];
              currentMsg.toolCalls.push({ tool: data.tool, input: data.input });
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === 'assistant') {
                  return [...prev.slice(0, -1), { ...currentMsg }];
                }
                return [...prev, { ...currentMsg }];
              });
            } else if (data.event === 'tool_result') {
              setLoadingStep('Processing Result');
              if (currentMsg.toolCalls) {
                const tc = currentMsg.toolCalls.find(t => t.tool === data.tool && !t.result);
                if (tc) tc.result = data.result;
              }
              setMessages((prev) => [...prev.slice(0, -1), { ...currentMsg }]);
            } else if (data.event === 'done') {
              setLoadingStep('');
              // Refresh sidebar triggers on first message to show title
              if (messages.length <= 1) {
                window.dispatchEvent(new Event('chat-updated'));
              }
            }
          } catch (e) {
            console.error('Error parsing SSE:', e);
          }
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ai-stage relative flex flex-col h-full min-h-0 bg-slate-50 text-slate-900 overflow-hidden">
      {/* Desktop Header Overlay */}
      <header className="ai-topbar hidden lg:flex px-8 py-5 items-center justify-between border-b border-slate-200 backdrop-blur-md sticky top-0 z-40 bg-white/80">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full bg-violet-500 shadow-[0_0_10px_rgba(139,92,246,0.3)] animate-pulse" />
            <h2 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.25em]">
              MatchOps Command
            </h2>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="p-2 text-slate-400 hover:text-slate-900 transition-colors">
            <MoreVertical className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Messages Container */}
      <div ref={messagesContainerRef} className="flex-1 min-h-0 overflow-y-auto custom-scrollbar pt-4 pb-48 md:pb-56">
        <div className="max-w-4xl mx-auto px-4 md:px-8 space-y-12">
          {messages.length === 0 && (
            <div className="ai-hero py-20 text-center animate-in fade-in zoom-in duration-1000">
              <div className="ai-hero-badge w-16 h-16 rounded-2xl bg-white border border-slate-100 flex items-center justify-center mx-auto mb-8 shadow-xl shadow-slate-200/50">
                <BrainCircuit className="w-8 h-8 text-violet-500" />
              </div>
              <h1 className="text-4xl md:text-5xl font-black tracking-tighter text-slate-900 mb-4">
                MatchOps AI <br />
                <span className="text-slate-400 font-medium">Tender & Talent Intelligence.</span>
              </h1>
              <p className="text-slate-500 text-sm font-medium max-w-md mx-auto">
                Analyze tenders, shortlist candidates, and run high-confidence workspace queries from one command center.
              </p>
            </div>
          )}

          {messages.map((msg, i) => {
            const matchCards = msg.role === 'assistant' ? getMatchCardsFromMessage(msg) : [];
            const resumeCards = msg.role === 'assistant' ? getResumeCardsFromMessage(msg) : [];
            const tenderCards = msg.role === 'assistant' ? getTenderCardsFromMessage(msg) : [];

            return (
              <div
                key={i}
                className={cn(
                  "message-lift group relative animate-in fade-in duration-700",
                  msg.role === 'user' ? "flex justify-end" : "flex justify-start"
                )}
              >
                <div className={cn(
                  "max-w-[85%] lg:max-w-[70%] relative",
                  msg.role === 'user' ? "" : "pl-12"
                )}>
                  {/* Assistant Icon */}
                  {msg.role === 'assistant' && (
                    <div className="absolute left-0 top-0 w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-slate-400 shadow-sm">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  {/* Message Bubble */}
                  <div className={cn(
                    "relative transition-all duration-500",
                    msg.role === 'user'
                      ? "prompt-pill bg-violet-600 text-white px-6 py-4 rounded-[1.8rem] shadow-xl shadow-violet-200/50"
                      : "text-slate-800"
                  )}>
                    {msg.role === 'user' ? (
                      <div className="text-[14px] font-semibold leading-relaxed tracking-tight">{msg.content}</div>
                    ) : SHOW_STRUCTURED_RESPONSE_CARDS && resumeCards.length > 0 ? (
                      <ResumeInlineAnswer
                        content={msg.content.replace(/\[\[CHOICE:.*?\]\]/g, '').trim()}
                        cards={resumeCards}
                      />
                    ) : (
                      <div className="prose prose-slate prose-sm max-w-none text-[15px] leading-relaxed">
                        <MarkdownRenderer content={msg.content.replace(/\[\[CHOICE:.*?\]\]/g, '').trim()} />
                      </div>
                    )}
                  </div>

                  {/* Execution Traces */}
                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div className="mt-8 pt-8 border-t border-slate-200 space-y-4">
                      <div className="flex items-center gap-3 mb-2 px-1">
                        <Terminal className="w-3.5 h-3.5 text-slate-400" />
                        <span className="text-[9px] font-bold uppercase tracking-[0.3em] text-slate-400">Execution Trace</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {msg.toolCalls.map((tc, j) => (
                          <button
                            key={j}
                            onClick={() => toggleToolLog(i, j)}
                            className={cn(
                              "flex items-center gap-3 px-4 py-2 rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all",
                              tc.result
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-100'
                                : 'bg-amber-50 text-amber-700 border border-amber-100 animate-pulse'
                            )}
                          >
                            {tc.tool}
                            <span className="opacity-40 font-mono">{tc.expanded ? '—' : '+'}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {msg.toolCalls?.map((tc, j) => tc.expanded && (
                    <div key={j} className="mt-4 p-5 bg-slate-100/50 rounded-2xl border border-slate-200 shadow-inner animate-in slide-in-from-top-2 duration-300">
                      {tc.input && (
                        <div className="mb-4 text-[11px] font-mono whitespace-pre overflow-x-auto text-slate-500 bg-white p-4 rounded-xl border border-slate-200">
                          {JSON.stringify(tc.input, null, 2)}
                        </div>
                      )}
                      {tc.result && (
                        <div className="max-h-60 overflow-y-auto bg-white p-4 rounded-xl border border-slate-200 text-[12px] custom-scrollbar">
                          <RenderToolResult result={tc.result} />
                        </div>
                      )}
                    </div>
                  ))}
                  {SHOW_STRUCTURED_RESPONSE_CARDS && matchCards.length > 0 && (
                    <div className="mt-6">
                      <ChatMatchCards cards={matchCards} />
                    </div>
                  )}

                  {SHOW_STRUCTURED_RESPONSE_CARDS && tenderCards.length > 0 && (
                    <div className="mt-6">
                      <ChatTenderCards cards={tenderCards} />
                    </div>
                  )}

                </div>
              </div>
            );
          })}
          {loading && (
            <ThinkingIndicator message={loadingStep} />
          )}
          <div ref={bottomRef} className="h-4" />
        </div>
      </div>

      {/* Input Dock */}
      <div className="chat-input-shell fixed bottom-0 left-0 right-0 lg:left-[var(--sidebar-offset)] z-30 p-4 md:px-6 md:pb-6 pointer-events-none">
        <div className="mx-auto w-full max-w-3xl pointer-events-auto flex flex-col items-center">
          <ChatChoices
            question={pendingQuestion}
            choices={pendingChoices}
            onSelect={handleChoiceSelect}
            disabled={loading}
          />

          <div className={cn(
            "ai-dock w-full bg-white border border-slate-200 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.1)] transition-all duration-500 group relative overflow-hidden",
            pendingChoices.length > 0 ? "rounded-b-[2rem] border-t-0" : "rounded-[2rem]",
            "focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-500/5"
          )}>
            <div className="flex items-end gap-1 px-3 py-2 md:px-4 md:py-2.5">
              <button className="p-2.5 text-slate-400 hover:text-slate-600 transition-colors shrink-0">
                <Paperclip className="w-5 h-5" />
              </button>

              <div className="flex-1 flex flex-col min-w-0 pb-0.5">
                <textarea
                  ref={textareaRef}
                  value={input}
                  rows={1}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="Ask MatchOps AI or type '/' for commands..."
                  className="w-full bg-transparent py-2 text-[14px] font-semibold text-slate-900 outline-none placeholder:text-slate-300 resize-none max-h-32 custom-scrollbar"
                  disabled={loading}
                />
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-violet-50 border border-violet-100">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-500 shadow-[0_0_5px_rgba(139,92,246,0.5)]" />
                    <span className="text-[8px] font-black text-violet-600 uppercase tracking-widest">AI Workspace Online</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 pb-1">
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || loading}
                  className={cn(
                    "p-2.5 rounded-[1.1rem] transition-all active:scale-90 flex items-center justify-center",
                    input.trim() ? "bg-violet-600 text-white shadow-lg shadow-violet-200" : "bg-slate-100 text-slate-300"
                  )}
                >
                  <Send className={cn("w-4 h-4", loading && "animate-pulse")} />
                </button>
              </div>
            </div>
          </div>
          <p className="mt-4 text-[10px] text-slate-400 font-medium text-center">
            AI can make mistakes. Always verify critical tender information.
          </p>
        </div>
      </div>
    </div>
  );
}
