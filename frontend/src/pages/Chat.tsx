import { useState, useRef, useEffect } from 'react';
import {
  Send,
  Bot,
  Sparkles,
  History,
  Briefcase,
  BrainCircuit,
  Command,
  Zap,
  ShieldCheck,
  Terminal,
  ChevronDown,
  ChevronRight,
  ExternalLink
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import { cn } from '../utils/utils';
import { getResume, listResumes } from '../api/client';
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
}

interface ParsedChoice {
  label: string;
  value: string;
}

let resumeListCache: Promise<Resume[]> | null = null;

function gradeColor(pct: number) {
  if (pct >= 75) return { bg: 'bg-emerald-50/60', text: 'text-emerald-700', border: 'border-emerald-200/50' };
  if (pct >= 50) return { bg: 'bg-amber-50/60', text: 'text-amber-700', border: 'border-amber-200/50' };
  if (pct >= 25) return { bg: 'bg-orange-50/60', text: 'text-orange-700', border: 'border-orange-200/50' };
  return { bg: 'bg-rose-50/60', text: 'text-rose-700', border: 'border-rose-200/50' };
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
      };
    })
    .filter((item): item is ParsedResumeCard => item !== null);
}

function parseResumeCardsFromContent(content?: string): ParsedResumeCard[] {
  if (!content || !content.includes('**')) return [];

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

function MiniBadge({ label, value, max }: { label: string; value?: number; max: number }) {
  const pct = max > 0 ? ((value || 0) / max) * 100 : 0;
  const color = gradeColor(pct);
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider ${color.bg} ${color.text} border ${color.border}`}>
      {label}: <span className="text-slate-900">{compactScore(value)}</span>
      <span className="text-slate-300 font-medium">/ {max}</span>
    </span>
  );
}

function CandidatePhoto({ candidateName, resumeId, photoUrl, className }: { candidateName: string; resumeId?: number; photoUrl?: string; className: string }) {
  const [resolvedPhotoUrl, setResolvedPhotoUrl] = useState(() => {
    const url = photoUrl?.trim();
    return url && url.toLowerCase() !== 'n/a' ? url : '';
  });
  const initials = candidateName
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2);

  useEffect(() => {
    if (resolvedPhotoUrl) return;

    let cancelled = false;

    async function resolvePhoto() {
      try {
        if (resumeId) {
          const detail = await getResume(resumeId);
          if (!cancelled && detail.photo_url) {
            setResolvedPhotoUrl(detail.photo_url);
            return;
          }
        }

        const resumes = await getCachedResumes();
        const targetName = normalizeCandidateName(candidateName);
        const match = resumes.find((resume) => normalizeCandidateName(resume.name) === targetName);
        if (!cancelled && match?.photo_url) {
          setResolvedPhotoUrl(match.photo_url);
        }
      } catch {
        // Keep initials fallback when a photo cannot be resolved.
      }
    }

    resolvePhoto();
    return () => {
      cancelled = true;
    };
  }, [candidateName, resumeId, resolvedPhotoUrl]);

  if (resolvedPhotoUrl) {
    return (
      <img
        src={resolvedPhotoUrl}
        alt={candidateName}
        className={className}
        onError={() => setResolvedPhotoUrl('')}
      />
    );
  }

  return (
    <div className={`${className} bg-slate-100 flex items-center justify-center text-slate-500 text-sm font-bold`}>
      {initials}
    </div>
  );
}

function ChatMatchRow({ item, rank }: { item: ParsedMatchCard; rank: number }) {
  const [open, setOpen] = useState(false);
  const color = gradeColor(item.fitScore);

  return (
    <div className={`border rounded-xl overflow-hidden bg-white ${color.border}`}>
      <button
        onClick={() => setOpen((value) => !value)}
        className="w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-slate-50 transition-colors"
      >
        <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${color.bg} ${color.text} shrink-0`}>
          {rank}
        </span>
        <CandidatePhoto
          candidateName={item.candidateName}
          resumeId={item.resumeId}
          photoUrl={item.photoUrl}
          className="w-12 h-12 rounded-xl object-cover border-2 border-slate-100 shrink-0"
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-black text-slate-900 truncate uppercase">{item.candidateName}</p>
            {item.resumeId && (
              <Link
                to={`/resumes/${item.resumeId}`}
                className="flex items-center gap-1.5 text-[10px] text-blue-600 font-bold hover:text-blue-700 transition-colors bg-blue-50 px-2.5 py-1 rounded-lg border border-blue-100 uppercase tracking-wider"
              >
                Open Resume <ExternalLink className="w-2.5 h-2.5" />
              </Link>
            )}
          </div>
          <p className="text-xs text-slate-500 -mt-0.5 italic truncate">
            {item.designation || 'Profile'}{item.experienceYears ? ` - ${item.experienceYears}` : ''}
          </p>
          <div className="flex flex-wrap gap-1 mt-1">
            <MiniBadge label="Skills" value={item.breakdown.skills} max={35} />
            <MiniBadge label="Domain" value={item.breakdown.domain} max={25} />
            <MiniBadge label="Edu" value={item.breakdown.edu} max={15} />
            <MiniBadge label="Certs" value={item.breakdown.certs} max={15} />
            <MiniBadge label="Exp" value={item.breakdown.exp} max={10} />
          </div>
        </div>

        <div className="text-right shrink-0 w-28">
          <div className={`text-3xl font-black leading-none tracking-tighter ${color.text}`}>{item.fitScore.toFixed(0)}%</div>
          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mt-1">Match Index</p>
          <div className="text-[9px] font-black text-slate-500 mt-2 flex items-center justify-end gap-1 uppercase">
            <span className="bg-white px-1.5 py-0.5 rounded border border-slate-200">ST: {compactScore(item.structuredScore)}</span>
            <span className="bg-white px-1.5 py-0.5 rounded border border-slate-200">AI: {compactScore(item.aiScore)}</span>
          </div>
        </div>
        <ChevronDown className={cn("w-5 h-5 text-slate-400 shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="px-4 py-4 bg-slate-50 border-t border-slate-100 grid gap-4 md:grid-cols-2">
          {item.explanation && (
            <div>
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">AI Judgment</p>
              <p className="text-xs text-slate-600 leading-relaxed italic border-l-4 border-indigo-100 pl-3">{item.explanation}</p>
            </div>
          )}
          {item.strengths.length > 0 && (
            <div>
              <p className="text-[10px] font-black text-emerald-700 uppercase tracking-widest mb-2">Top Strengths</p>
              <div className="space-y-1.5">
                {item.strengths.map((strength) => (
                  <p key={strength} className="text-[11px] text-slate-600 font-medium">{strength}</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ChatResumeCards({ cards }: { cards: ParsedResumeCard[] }) {
  if (cards.length === 0) return null;

  return (
    <div className="bg-white rounded-2xl border border-slate-100 overflow-hidden shadow-sm">
      <div className="flex items-center gap-4 px-5 py-4 border-b border-slate-50">
        <div className="w-1.5 h-10 rounded-full bg-blue-50 border-l-4 border-blue-200/50" />
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-black text-slate-900 uppercase tracking-tight">Candidate Profiles</h3>
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">
            {cards.length} validated resume result{cards.length === 1 ? '' : 's'}
          </p>
        </div>
      </div>

      <div className="p-4 space-y-3 bg-slate-50/30">
        {cards.map((item, idx) => (
          <div key={`${item.resumeId || item.candidateName}-${idx}`} className="border border-slate-100 rounded-xl overflow-hidden bg-white">
            <div className="flex items-center gap-4 px-4 py-3">
              <span className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold bg-blue-50 text-blue-700 shrink-0">
                {idx + 1}
              </span>
              <CandidatePhoto
                candidateName={item.candidateName}
                resumeId={item.resumeId}
                className="w-12 h-12 rounded-xl object-cover border-2 border-slate-100 shrink-0"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-black text-slate-900 truncate uppercase">{item.candidateName}</p>
                  {item.resumeId && (
                    <Link
                      to={`/resumes/${item.resumeId}`}
                      className="flex items-center gap-1.5 text-[10px] text-blue-600 font-bold hover:text-blue-700 transition-colors bg-blue-50 px-2.5 py-1 rounded-lg border border-blue-100 uppercase tracking-wider"
                    >
                      Open Resume <ExternalLink className="w-2.5 h-2.5" />
                    </Link>
                  )}
                  {item.relevance && <span className="text-[10px] text-emerald-600 font-black shrink-0">{item.relevance}</span>}
                </div>
                <p className="text-xs text-slate-500 -mt-0.5 italic truncate">
                  {item.role || 'Profile'}{item.experience ? ` - ${item.experience}` : ''}
                </p>
                {item.education && (
                  <p className="text-[11px] text-slate-500 font-medium mt-1 line-clamp-2">
                    {item.education}
                  </p>
                )}
                {item.skills.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {item.skills.map((skill) => (
                      <span key={skill} className="px-2 py-0.5 rounded-lg bg-slate-50 border border-slate-100 text-[10px] font-bold text-slate-600">
                        {skill}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="text-right shrink-0 hidden sm:block">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Resume</p>
                <p className="text-lg font-black text-blue-700">Profile</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChatMatchCards({ cards }: { cards: ParsedMatchCard[] }) {
  if (cards.length === 0) return null;

  const groups = cards.reduce<Record<string, ParsedMatchCard[]>>((acc, card) => {
    acc[card.roleTitle] = acc[card.roleTitle] || [];
    acc[card.roleTitle].push(card);
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      {Object.entries(groups).map(([role, roleCards]) => {
        const sorted = [...roleCards].sort((a, b) => b.fitScore - a.fitScore);
        const topScore = sorted[0]?.fitScore || 0;
        const topColor = gradeColor(topScore);
        return (
          <div key={role} className="bg-white rounded-2xl border border-slate-100 overflow-hidden shadow-sm">
            <div className="flex items-center gap-4 px-5 py-4 border-b border-slate-50">
              <div className={`w-1.5 h-10 rounded-full ${topColor.bg} border-l-4 ${topColor.border}`} />
              <div className="flex-1 min-w-0">
                <h3 className="text-base font-black text-slate-900 uppercase tracking-tight truncate">{role}</h3>
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">
                  {sorted.length} candidate{sorted.length === 1 ? '' : 's'} from stored match results
                </p>
              </div>
              <div className="text-right shrink-0">
                <div className={`text-2xl font-black ${topColor.text}`}>{topScore.toFixed(0)}%</div>
                <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Top Match</div>
              </div>
            </div>
            <div className="p-4 space-y-3 bg-slate-50/30">
              {sorted.map((item, idx) => (
                <ChatMatchRow key={`${item.resumeId || item.candidateName}-${item.roleTitle}`} item={item} rank={idx + 1} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ChatChoices({ question, choices, onSelect, disabled }: { question?: string; choices: ParsedChoice[]; onSelect: (label: string, value: string) => void; disabled?: boolean }) {
  if (choices.length === 0) return null;

  return (
    <div className="w-full mb-[-1.5rem] animate-in slide-in-from-bottom-4 fade-in duration-500 relative z-30">
      <div className="w-full bg-white border border-slate-200 rounded-t-[2.5rem] rounded-b-[1.5rem] shadow-[0_-20px_50px_-15px_rgba(0,0,0,0.1)] overflow-hidden">
        <div className="flex items-center gap-3 px-8 py-5 border-b border-slate-100/50 bg-slate-50/50">
            <div className="w-8 h-8 rounded-xl bg-violet-600 flex items-center justify-center shadow-lg shadow-violet-200">
                <BrainCircuit className="w-4 h-4 text-white" />
            </div>
            <div className="flex-1">
                <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Agentic Intelligence</h3>
                <p className="text-[11px] font-bold text-slate-800 line-clamp-1">{question || "Awaiting your selection to proceed..."}</p>
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
                className="group flex items-center gap-4 w-full px-5 py-4 bg-slate-50/50 hover:bg-violet-600 border border-slate-100 rounded-2xl transition-all shadow-sm hover:shadow-lg hover:shadow-violet-200 active:scale-[0.98] disabled:opacity-50"
              >
                <div className="w-8 h-8 rounded-full bg-slate-800 text-white flex items-center justify-center text-[10px] font-black group-hover:bg-white group-hover:text-violet-600 transition-colors shrink-0 shadow-sm">
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

export default function Chat() {
  const [messages, setMessages] = useState<ChatMsg[]>(() => {
    const saved = localStorage.getItem('chat_messages');
    return saved ? JSON.parse(saved) : [];
  });
  const [input, setInput] = useState('');
  const [pendingChoices, setPendingChoices] = useState<ParsedChoice[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState('');
  const [placeholder, setPlaceholder] = useState('Instruct the AI assistant...');
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState(() => {
    const saved = localStorage.getItem('chat_session_id');
    if (saved) return saved;
    const newId = crypto.randomUUID();
    localStorage.setItem('chat_session_id', newId);
    return newId;
  });
  const [currentTool, setCurrentTool] = useState('');
  const [showThought, setShowThought] = useState<Record<number, boolean>>({});
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const prompts = [
      "Analyze tunnel project veterans...",
      "Identify candidates with 20+ yrs exp...",
      "Compare PhD vs Masters in Civil Eng...",
      "Extract key skills from Tender NH-44...",
      "Who are our top mountain terrain experts?"
    ];
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % prompts.length;
      setPlaceholder(`Try: "${prompts[i]}"`);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  useEffect(() => {
    localStorage.setItem('chat_messages', JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    const handleClear = () => {
      setMessages([]);
      const newId = crypto.randomUUID();
      localStorage.setItem('chat_session_id', newId);
      localStorage.removeItem('chat_messages');
    };
    window.addEventListener('clear-chat-history', handleClear);
    return () => window.removeEventListener('clear-chat-history', handleClear);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentTool]);

  const toggleThought = (idx: number) => {
    setShowThought(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  const toggleToolLog = (msgIndex: number, toolIndex: number) => {
    setMessages(prev => {
      const next = [...prev];
      const msg = { ...next[msgIndex] };
      if (msg.toolCalls) {
        msg.toolCalls = [...msg.toolCalls];
        msg.toolCalls[toolIndex] = {
          ...msg.toolCalls[toolIndex],
          expanded: !msg.toolCalls[toolIndex].expanded
        };
        next[msgIndex] = msg;
      }
      return next;
    });
  };

  const handleChoiceSelect = (label: string, value: string) => {
    setPendingChoices([]);
    setPendingQuestion('');
    handleSend(value, label);
  };

  const handleSend = async (overrideMsg?: string, displayLabel?: string) => {
    const msgToSubmit = overrideMsg || input.trim();
    if (!msgToSubmit || loading) return;

    if (!overrideMsg) setInput('');
    setPendingChoices([]);
    setPendingQuestion('');
    
    const displayMsg = displayLabel ? `I've selected: ${displayLabel}` : msgToSubmit;
    setMessages((prev) => [...prev, { role: 'user', content: displayMsg }]);
    setLoading(true);
    setCurrentTool('');
    let thinkingText = '';

    const toolCalls: { tool: string; input?: any; result?: string }[] = [];

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: msgToSubmit }),
      });

      if (!response.ok) throw new Error('Chat request failed');

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No stream');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.event === 'thinking') {
              setCurrentTool('Thinking...');
            } else if (event.event === 'thought') {
              thinkingText += event.token;
              setCurrentTool(`Thinking: ${thinkingText.slice(-30)}...`);
            } else if (event.event === 'tool_call') {
              setCurrentTool(`Using ${event.tool}...`);
              toolCalls.push({ tool: event.tool, input: event.input });
            } else if (event.event === 'tool_result') {
              const idx = [...toolCalls].reverse().findIndex(tc => tc.tool === event.tool);
              if (idx !== -1) {
                const actualIdx = toolCalls.length - 1 - idx;
                toolCalls[actualIdx].result = event.result;
              }
            } else if (event.event === 'answer') {
              setCurrentTool('');
              const content = event.content;
              const choiceRegex = /\[\[CHOICE:\s*(.*?)\s*\|\s*(.*?)\s*\]\]/g;
              const choices: ParsedChoice[] = [];
              let match;
              while ((match = choiceRegex.exec(content)) !== null) {
                choices.push({ label: match[1], value: match[2] });
              }

              if (choices.length > 0) {
                setPendingChoices(choices);
                // Extract question text before the choices tag
                const question = content.split('[[CHOICE:')[0].trim();
                setPendingQuestion(question);
              } else {
                setMessages((prev) => [
                  ...prev,
                  { role: 'assistant', content, thought: thinkingText, toolCalls: [...toolCalls] },
                ]);
              }
            } else if (event.event === 'error') {
              setCurrentTool('');
              setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: `Error: ${event.message}` },
              ]);
            }
          } catch { }
        }
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
      setCurrentTool('');
    }
  };

  const RenderToolResult = ({ result }: { result: string }) => {
    if (!result) return null;

    // Simple regex to split text and SQL blocks
    const parts = result.split(/(```sql[\s\S]*?```)/g);

    return (
      <div className="space-y-2">
        {parts.map((part, idx) => {
          if (part.startsWith('```sql')) {
            const sql = part.replace(/```sql|```/g, '').trim();
            return (
              <div key={idx} className="my-2">
                <p className="text-[9px] text-blue-400 font-bold uppercase mb-1 flex items-center gap-1">
                  <span className="p-0.5 bg-blue-500 rounded text-white text-[8px]">SQL</span> Generated Query
                </p>
                <div className="bg-slate-900 text-green-400 p-3 rounded-lg font-mono text-[10px] leading-relaxed border border-slate-800 shadow-inner overflow-x-auto whitespace-pre">
                  {sql}
                </div>
              </div>
            );
          }
          if (!part.trim()) return null;
          return (
            <div key={idx} className="text-[10px] text-gray-600 leading-normal whitespace-pre-wrap">
              {part}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="flex h-[calc(100vh-64px)] bg-slate-50 overflow-hidden font-sans">

      {/* Primary Interaction Console */}
      <div className="flex-1 flex flex-col relative overflow-hidden h-full">
        {/* Messages Scroll Area */}
        <div className="flex-1 overflow-y-auto px-4 md:px-6 py-10 custom-scrollbar">
          <div className="w-full max-w-4xl mx-auto space-y-8 md:space-y-12">
            {messages.length === 0 && (
              <div className="space-y-16 py-12 animate-in fade-in slide-in-from-bottom-8 duration-1000">
                <div className="text-center space-y-4">
                  <div className="w-24 h-24 bg-gradient-to-br from-violet-600 to-fuchsia-600 rounded-[2.5rem] flex items-center justify-center mx-auto shadow-2xl shadow-violet-200 rotate-3 group hover:rotate-0 transition-transform duration-500">
                    <Sparkles className="w-12 h-12 text-white" />
                  </div>
                  <h1 className="text-5xl font-black tracking-tighter text-slate-900 mt-6">How can I assist <br /><span className="text-violet-600">your strategy?</span></h1>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl mx-auto">
                  {[
                    { txt: 'Identify candidates with 4-lane highway experience', icon: <Briefcase className="w-4 h-4 text-emerald-600" /> },
                    { txt: 'Compare PhD vs Master candidates in Civil Eng', icon: <Command className="w-4 h-4 text-amber-600" /> },
                    { txt: 'Who are our top tunnel project veterans?', icon: <History className="w-4 h-4 text-blue-600" /> },
                    { txt: 'Analyze tender TND-0045 requirements', icon: <Zap className="w-4 h-4 text-violet-600" /> },
                  ].map((q) => (
                    <button
                      key={q.txt}
                      onClick={() => { setInput(q.txt); }}
                      className="group text-left p-6 rounded-[2rem] bg-white border border-slate-100 hover:border-violet-300 hover:shadow-2xl hover:shadow-violet-100 transition-all duration-300 hover:-translate-y-1 active:scale-95 shadow-sm"
                    >
                      <div className="w-10 h-10 rounded-xl bg-slate-50 group-hover:bg-violet-50 flex items-center justify-center mb-5 transition-colors">
                        {q.icon}
                      </div>
                      <span className="text-sm font-black text-slate-700 block group-hover:text-violet-900 transition-colors leading-snug">{q.txt}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => {
              const matchCards = msg.role === 'assistant' ? getMatchCardsFromMessage(msg) : [];
              const resumeCards = msg.role === 'assistant' && matchCards.length === 0 ? getResumeCardsFromMessage(msg) : [];
              return (
              <div key={i} className={cn(
                "flex animate-in fade-in slide-in-from-bottom-4 duration-500",
                msg.role === 'user' ? 'justify-end' : 'justify-start'
              )}>
                <div className={cn(
                  "max-w-[90%] lg:max-w-[85%] rounded-[2rem] px-5 py-4",
                  msg.role === 'user'
                    ? 'bg-gradient-to-br from-violet-600 to-indigo-700 text-white shadow-xl shadow-violet-200/50'
                    : 'bg-white border border-slate-100 shadow-2xl shadow-slate-100/50 relative overflow-hidden'
                )}>

                  {/* AI Label */}
                  {msg.role === 'assistant' && (
                    <div className="flex items-center gap-2 mb-3 text-[9px] font-black uppercase tracking-[0.2em] text-violet-600">
                      <div className="w-4 h-4 rounded-full bg-violet-600 flex items-center justify-center">
                        <Bot className="w-2.5 h-2.5 text-white" />
                      </div>
                      Assistant Intelligence
                    </div>
                  )}

                  {/* Logic Trace Expansion */}
                  {msg.thought && (
                    <div className="mb-6 rounded-[1.2rem] bg-slate-50 border border-slate-100 overflow-hidden group/thought">
                      <button
                        onClick={() => toggleThought(i)}
                        className="w-full px-5 py-3 flex items-center gap-3 text-[9px] uppercase tracking-widest font-black text-slate-500 hover:text-violet-600 transition-colors bg-white/40"
                      >
                        <BrainCircuit className="w-4 h-4 text-violet-500" />
                        View Execution Logic
                        <span className="ml-auto opacity-50 font-bold group-hover/thought:translate-x-1 transition-transform">{showThought[i] ? 'Minimize' : 'Expand \u2192'}</span>
                      </button>
                      {showThought[i] && (
                        <div className="p-6 text-[11px] text-slate-500 italic leading-relaxed font-bold border-t border-slate-100 bg-white/20">
                          {msg.thought}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Content Render */}
                  <div className={cn(
                    "text-[15px] leading-relaxed",
                    msg.role === 'user' ? 'text-white' : 'text-slate-800'
                  )}>
                    {msg.role === 'user' ? (
                      <div className="font-bold tracking-tight">{msg.content}</div>
                    ) : matchCards.length > 0 ? (
                      <ChatMatchCards cards={matchCards} />
                    ) : resumeCards.length > 0 ? (
                      <ChatResumeCards cards={resumeCards} />
                    ) : (
                      <MarkdownRenderer content={msg.content.replace(/\[\[CHOICE:.*?\]\]/g, '').trim()} />
                    )}
                  </div>

                  {/* Execution History Bubbles */}
                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div className="mt-10 flex flex-wrap gap-2 pt-6 border-t border-slate-50">
                      <span className="text-[9px] w-full font-black uppercase tracking-[0.3em] text-slate-300 mb-2">Computational Traces</span>
                      {msg.toolCalls.map((tc, j) => (
                        <button
                          key={j}
                          onClick={() => toggleToolLog(i, j)}
                          className={cn(
                            "flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all",
                            tc.result ? 'bg-emerald-50 text-emerald-600 border border-emerald-100' : 'bg-amber-50 text-amber-600 border border-amber-100 animate-pulse'
                          )}
                        >
                          <Terminal className="w-3.5 h-3.5" /> {tc.tool}
                          {tc.expanded && <span className="ml-2 bg-white/50 px-1 rounded">Log</span>}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Expanded Logs UI */}
                  {msg.toolCalls?.map((tc, j) => tc.expanded && (
                    <div key={j} className="mt-4 p-5 bg-slate-50 rounded-2xl border border-slate-100 shadow-inner animate-in slide-in-from-top-2 duration-300">
                      {tc.input && (
                        <div className="mb-4">
                          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Request Parameters</p>
                          <pre className="text-[10px] bg-white p-3 rounded-xl border border-slate-100 text-slate-600 font-mono">{JSON.stringify(tc.input, null, 2)}</pre>
                        </div>
                      )}
                      {tc.result && (
                        <div>
                          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Resolution Output</p>
                          <div className="max-h-60 overflow-y-auto bg-white p-4 rounded-xl border border-slate-100">
                            <RenderToolResult result={tc.result} />
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
              );
            })}

            {loading && (
              <div className="flex justify-start animate-pulse">
                <div className="w-12 h-12 bg-slate-100 rounded-full flex items-center justify-center">
                  <div className="w-6 h-6 border-2 border-violet-600 border-t-transparent rounded-full animate-spin" />
                </div>
              </div>
            )}
          </div>
          <div ref={bottomRef} className="h-4" />
        </div>

        {/* ChatGPT Style Command Dock */}
        <div className="w-full bg-white border-t border-slate-100 px-4 md:px-8 py-4 md:py-6 z-20">
          <div className="w-full max-w-4xl mx-auto flex flex-col gap-0">
            <ChatChoices
              question={pendingQuestion}
              choices={pendingChoices}
              onSelect={handleChoiceSelect}
              disabled={loading}
            />
            <div className={cn(
              "relative p-1.5 md:p-2 bg-white border border-slate-200/60 rounded-[1.5rem] md:rounded-[2rem] transition-all duration-500 group",
              input.trim() ? "shadow-[0_10px_40px_-10px_rgba(124,58,237,0.15)] ring-1 ring-violet-500/10" : "shadow-sm",
              "focus-within:ring-4 focus-within:ring-violet-500/5 focus-within:border-violet-500/30"
            )}>
              <div className="flex items-end gap-1 md:gap-2">
                <div className="pl-3 md:pl-5 pb-3 md:pb-4 text-slate-300 group-focus-within:text-violet-500 transition-colors shrink-0">
                  <Command className={cn("w-5 h-5", loading && "animate-pulse text-violet-600")} />
                </div>
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
                  placeholder={placeholder}
                  className="flex-1 bg-transparent py-3 md:py-4 px-2 md:px-3 text-[14px] md:text-[15px] font-bold text-slate-800 outline-none placeholder:text-slate-300 resize-none max-h-32 md:max-h-48 custom-scrollbar transition-all duration-300"
                  disabled={loading}
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || loading}
                  className={cn(
                    "mb-0.5 md:mb-1 p-3 md:px-6 md:py-4 rounded-[1.2rem] md:rounded-[1.5rem] text-white transition-all active:scale-90 flex items-center gap-3 overflow-hidden group/btn relative shrink-0",
                    input.trim() ? "bg-violet-600 shadow-lg shadow-violet-200 hover:bg-violet-700" : "bg-slate-50 text-slate-300 cursor-not-allowed"
                  )}
                >
                  <div className="absolute inset-0 bg-gradient-to-r from-violet-600 via-fuchsia-500 to-violet-600 bg-[length:200%_100%] animate-shimmer opacity-0 group-hover/btn:opacity-100 transition-opacity" />
                  <span className="text-[10px] md:text-xs font-black uppercase tracking-widest hidden sm:inline relative z-10">
                    {loading ? '...' : 'Execute'}
                  </span>
                  <Send className={cn("w-4 h-4 md:w-5 h-5 relative z-10", loading && "animate-bounce")} />
                </button>
              </div>
            </div>
            <div className="mt-4 text-center">
              <p className="text-[8px] md:text-[9px] font-black text-slate-300 uppercase tracking-[0.3em] flex items-center justify-center gap-2">
                <ShieldCheck className="w-3 h-3 text-emerald-400" /> Secure Agentic Workspace
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
