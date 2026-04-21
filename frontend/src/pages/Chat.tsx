import { useState, useRef, useEffect } from 'react';
import {
  Send,
  Bot,
  BrainCircuit,
  Terminal,
  ChevronRight,
  ExternalLink,
  Paperclip,
  MoreVertical,
  Plus,
  Share2,
  Users
} from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import { cn } from '../utils/utils';
import { listResumes, getChatHistory } from '../api/client';
import type { Resume } from '../types';

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

let resumeListCache: Promise<Resume[]> | null = null;

function gradeColor(pct: number) {
  if (pct >= 75) return { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' };
  if (pct >= 50) return { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' };
  if (pct >= 25) return { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' };
  return { bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200' };
}

function normalizeCandidateName(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function getCachedResumes() {
  if (!resumeListCache) {
    resumeListCache = listResumes().catch((error) => {
      resumeListCache = null;
      throw error;
    });
  }
  return resumeListCache;
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
      const nameMatch = line.match(/^-\s+\*\*(.*?)\*\*\s+\(ID:(\d+)\)\s+\|\s+(.+)$/) || line.match(/^-\s+(.*?)\s+\(ID:(\d+)\)\s+\|\s+(.+)$/);
      if (!nameMatch) return null;

      const [, rawName, rawId, rest] = nameMatch;
      const parts = rest.split(/\s+\|\s+/);
      const fields = parseFields(`- ${parts.slice(2).join(' | ')}`);
      const skillsText = fields.skills || '';
      const skills = skillsText
        .split(',')
        .map((skill) => skill.trim())
        .filter(Boolean)
        .slice(0, 8);

      return {
        candidateName: rawName.trim(),
        resumeId: Number(rawId),
        role: parts[0]?.trim(),
        experience: parts[1]?.trim(),
        education: fields.education,
        skills,
        relevance: fields.relevance,
        photoUrl: fields.photo,
      };
    })
    .filter((item): item is ParsedResumeCard => item !== null);
}

function parseResumeCardsFromContent(content?: string): ParsedResumeCard[] {
  if (!content || !content.includes('**')) return [];
  if (content.includes('TND-')) return [];

  const cards: ParsedResumeCard[] = [];
  let current: ParsedResumeCard | null = null;

  for (const line of content.split('\n')) {
    const candidateMatch = line.match(/^\s*[-*]\s+\*\*(.+?)\*\*\s*$/);
    if (candidateMatch) {
      current = { candidateName: candidateMatch[1].trim(), skills: [] };
      cards.push(current);
      continue;
    }

    if (!current) continue;

    const fieldMatch = line.match(/^\s*[-*]\s+\*\*(Role|Experience|Education|Skills):\*\*\s*(.+)$/i);
    if (!fieldMatch) continue;

    const key = fieldMatch[1].toLowerCase();
    const value = fieldMatch[2].trim();
    if (key === 'role') current.role = value;
    if (key === 'experience') current.experience = value;
    if (key === 'education') current.education = value;
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
    ?.filter((tc) => tc.tool === 'sql_query_resumes' || tc.tool === 'search_resumes')
    .forEach((tc) => cards.push(...parseResumeCardsFromToolResult(tc.result)));

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
      let techs: string[] = [];
      let roles: string[] = [];

      // Parse next few lines for details
      let j = i + 1;
      while (j < lines.length && j < i + 10) {
        const nextLine = lines[j];
        if (nextLine.includes('Client:')) {
          const cm = nextLine.match(/Client:\s+(.+?)(?:\s+\||\s*$)/);
          if (cm) client = cm[1].trim();
          const dm = nextLine.match(/Duration:\s+(.+?)(?:\s+\||\s*$)/);
          if (dm) duration = dm[1].trim();
        }
        if (nextLine.includes('Technologies:')) {
          techs = nextLine.replace(/Technologies:\s+/, '').split(',').map(t => t.trim()).filter(Boolean);
        }
        if (nextLine.startsWith('Roles (')) {
          // Skip roles line
        } else if (nextLine.startsWith('- ') || nextLine.startsWith('  - ')) {
          roles.push(nextLine.replace(/^[\s-]*\s+/, '').trim());
        }

        if (lines[j + 1]?.startsWith('**TND-')) break; // Next tender start
        j++;
      }

      cards.push({
        tenderId,
        projectName,
        client,
        duration,
        techs,
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
            <Link
              to={`/resumes/${item.resumeId}`}
              className="flex items-center gap-1.5 text-[10px] text-violet-600 font-bold hover:text-white hover:bg-violet-600 transition-all bg-violet-50 px-2.5 py-1 rounded-lg border border-violet-100 uppercase tracking-wider"
            >
              Open Resume <ExternalLink className="w-2.5 h-2.5" />
            </Link>
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

function ChatResumeCards({ cards }: { cards: ParsedResumeCard[] }) {
  if (cards.length === 0) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
      {cards.map((item, idx) => (
        <div key={idx} className="group relative bg-white border border-slate-200 rounded-3xl p-5 transition-all hover:border-violet-200 hover:shadow-xl hover:shadow-slate-200/40 flex flex-col gap-4 overflow-hidden animate-in slide-in-from-bottom-4 duration-500" style={{ animationDelay: `${idx * 100}ms` }}>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-400 group-hover:bg-violet-50 group-hover:border-violet-100 group-hover:text-violet-600 transition-colors shrink-0 overflow-hidden">
                {item.photoUrl ? (
                  <img src={item.photoUrl} alt="" className="w-full h-full object-cover" />
                ) : (
                  <Users className="w-5 h-5" />
                )}
              </div>
              <div>
                <h3 className="text-sm font-black text-slate-900 uppercase tracking-tight leading-none mb-1">{item.candidateName}</h3>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{item.role || 'Personnel Profile'}</p>
              </div>
            </div>
            {item.resumeId && (
              <Link
                to={`/resumes/${item.resumeId}`}
                className="flex items-center gap-1.5 text-[9px] text-violet-600 font-black hover:bg-violet-600 hover:text-white transition-all bg-violet-50 px-3 py-2 rounded-xl border border-violet-100 uppercase tracking-wider shadow-sm"
              >
                Profile <ExternalLink className="w-2.5 h-2.5" />
              </Link>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="p-3 bg-slate-50/50 rounded-2xl border border-slate-100/50">
              <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Expertise</span>
              <p className="text-[11px] font-bold text-slate-600 truncate">{item.experience || 'N/A'}</p>
            </div>
            <div className="p-3 bg-slate-50/50 rounded-2xl border border-slate-100/50">
              <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Education</span>
              <p className="text-[11px] font-bold text-slate-600 truncate">{item.education || 'N/A'}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {item.skills.map((skill, si) => (
              <span key={si} className="px-2.5 py-1 rounded-lg bg-white border border-slate-100 text-[9px] font-bold text-slate-500 shadow-sm group-hover:border-violet-100 group-hover:text-violet-700 transition-all">
                {skill}
              </span>
            ))}
          </div>

          {item.relevance && (
            <div className="mt-auto pt-4 border-t border-slate-50 flex items-center justify-between">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Relevance Index</span>
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
            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-0.5 leading-none">Intelligence Protocol</h4>
            <p className="text-[13px] font-black text-slate-900 leading-tight">{question || 'Selection Required'}</p>
          </div>
          <span className="text-[9px] font-black text-violet-600 bg-violet-50 px-3 py-1.5 rounded-full uppercase tracking-widest border border-violet-100 animate-pulse">Decision Point</span>
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
  const [showThought, setShowThought] = useState<Record<number, boolean>>({});

  const textareaRef = useRef<HTMLTextAreaElement>(null);
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
        toolCalls: m.tool_calls ? JSON.parse(m.tool_calls).map((tc: any) => ({ ...tc, expanded: false })) : undefined
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
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
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
              currentMsg.thought = (currentMsg.thought || '') + data.content;
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
    <div className="flex flex-col h-screen bg-slate-50 text-slate-900">
      {/* Desktop Header Overlay */}
      <header className="hidden lg:flex px-8 py-5 items-center justify-between border-b border-slate-200 backdrop-blur-md sticky top-0 z-40 bg-white/80">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full bg-violet-500 shadow-[0_0_10px_rgba(139,92,246,0.3)] animate-pulse" />
            <h2 className="text-[11px] font-black text-slate-400 uppercase tracking-[0.25em]">
              Matcher Intelligence
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
      <div className="flex-1 overflow-y-auto custom-scrollbar pt-4 pb-32">
        <div className="max-w-4xl mx-auto px-4 md:px-8 space-y-12">
          {messages.length === 0 && (
            <div className="py-20 text-center animate-in fade-in zoom-in duration-1000">
              <div className="w-16 h-16 rounded-2xl bg-white border border-slate-100 flex items-center justify-center mx-auto mb-8 shadow-xl shadow-slate-200/50">
                <BrainCircuit className="w-8 h-8 text-violet-500" />
              </div>
              <h1 className="text-4xl md:text-5xl font-black tracking-tighter text-slate-900 mb-4">
                Matcher Intelligence <br />
                <span className="text-slate-400 font-medium">Unified Strategic Agent.</span>
              </h1>
              <p className="text-slate-500 text-sm font-medium max-w-md mx-auto">
                Ready to analyze tenders, match resumes, and execute strategic queries across your workspace.
              </p>
            </div>
          )}

          {messages.map((msg, i) => {
            const matchCards = msg.role === 'assistant' ? getMatchCardsFromMessage(msg) : [];
            const tenderCards = msg.role === 'assistant' && matchCards.length === 0 ? getTenderCardsFromMessage(msg) : [];
            const resumeCards = msg.role === 'assistant' && matchCards.length === 0 && tenderCards.length === 0 ? getResumeCardsFromMessage(msg) : [];

            return (
              <div
                key={i}
                className={cn(
                  "group relative animate-in fade-in duration-700",
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
                      ? "bg-violet-600 text-white px-6 py-4 rounded-[1.8rem] shadow-xl shadow-violet-200/50"
                      : "text-slate-800"
                  )}>
                    {msg.role === 'user' ? (
                      <div className="text-[14px] font-semibold leading-relaxed tracking-tight">{msg.content}</div>
                    ) : matchCards.length > 0 ? (
                      <ChatMatchCards cards={matchCards} />
                    ) : tenderCards.length > 0 ? (
                      <ChatTenderCards cards={tenderCards} />
                    ) : resumeCards.length > 0 ? (
                      <ChatResumeCards cards={resumeCards} />
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
                        <span className="text-[9px] font-bold uppercase tracking-[0.3em] text-slate-400">Strategic Resolution Log</span>
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
      <div className="fixed bottom-0 left-0 lg:left-[280px] right-0 p-4 md:p-10 pointer-events-none">
        <div className="max-w-4xl mx-auto w-full pointer-events-auto flex flex-col items-center">
          <ChatChoices
            question={pendingQuestion}
            choices={pendingChoices}
            onSelect={handleChoiceSelect}
            disabled={loading}
          />

          <div className={cn(
            "w-full bg-white border border-slate-200 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.1)] transition-all duration-500 group relative overflow-hidden",
            pendingChoices.length > 0 ? "rounded-b-[2rem] border-t-0" : "rounded-[2rem]",
            "focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-500/5"
          )}>
            <div className="flex items-end gap-1 px-4 py-2 md:px-5 md:py-3">
              <button className="p-3 text-slate-400 hover:text-slate-600 transition-colors shrink-0">
                <Paperclip className="w-5 h-5" />
              </button>

              <div className="flex-1 flex flex-col min-w-0 pb-1">
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
                  placeholder="Message Matcher or type '/' for commands..."
                  className="w-full bg-transparent py-3 text-[15px] font-semibold text-slate-900 outline-none placeholder:text-slate-300 resize-none max-h-48 custom-scrollbar"
                  disabled={loading}
                />
                <div className="flex items-center gap-2 mb-1">
                  <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-violet-50 border border-violet-100">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-500 shadow-[0_0_5px_rgba(139,92,246,0.5)]" />
                    <span className="text-[8px] font-black text-violet-600 uppercase tracking-widest">Agentic Workspace Active</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 pb-1.5">
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || loading}
                  className={cn(
                    "p-3 rounded-2xl transition-all active:scale-90 flex items-center justify-center",
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
