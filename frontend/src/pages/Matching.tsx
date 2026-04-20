import { useState, useEffect } from 'react';
import { listTenders, runMatching, getMatchResults, getResume } from '../api/client';
import type { Tender, MatchResponse, MatchResultItem, ResumeDetail } from '../types';
import { BrainCircuit } from 'lucide-react';
import ScoreBar from '../components/ScoreBar';

function gradeColor(pct: number) {
  if (pct >= 75) return { bg: 'bg-emerald-50/50', text: 'text-emerald-700', border: 'border-emerald-200/40' };
  if (pct >= 50) return { bg: 'bg-amber-50/50', text: 'text-amber-700', border: 'border-amber-200/40' };
  if (pct >= 25) return { bg: 'bg-orange-50/50', text: 'text-orange-700', border: 'border-orange-200/40' };
  return { bg: 'bg-rose-50/50', text: 'text-rose-700', border: 'border-rose-200/40' };
}

function Badge({ label, value, maxVal }: { label: string; value: number; maxVal: number }) {
  const pct = maxVal > 0 ? (value / maxVal) * 100 : 0;
  const c = gradeColor(pct);
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider ${c.bg} ${c.text} border ${c.border} shadow-sm`}>
      {label}: <span className="text-slate-900 mx-0.5">{value.toFixed(0)}</span> <span className="text-slate-300 font-medium">/ {maxVal}</span>
    </span>
  );
}

function SkillTag({ skill, matched }: { skill: string; matched: boolean }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium mr-1 mb-1 ${matched
        ? 'bg-green-100 text-green-700 border border-green-200'
        : 'bg-red-50 text-red-600 border border-red-200'
        }`}
    >
      {matched ? '\u2713' : '\u2717'} {skill}
    </span>
  );
}

function CandidateRow({ item, rank, reqExp, onViewResume }: { item: MatchResultItem; rank: number; reqExp: number; onViewResume: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false);
  const finalPct = item.final_score;
  const c = gradeColor(finalPct);
  const expMet = item.experience_years >= reqExp;

  return (
    <div className={`border rounded-xl mb-2 overflow-hidden ${c.border}`}>
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
      >
        <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${c.bg} ${c.text} shrink-0`}>
          {rank}
        </span>
        {item.photo_url ? (
          <img
            src={item.photo_url}
            alt={item.candidate_name}
            className="w-12 h-12 rounded-xl object-cover border-2 border-gray-100 shrink-0"
          />
        ) : (
          <div className="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center text-gray-500 text-sm font-bold shrink-0">
            {item.candidate_name.split(' ').map(n => n[0]).join('').slice(0, 2)}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-bold text-gray-900 group-hover:text-blue-600 truncate uppercase">{item.candidate_name}</p>
            <button
              onClick={(e) => { e.stopPropagation(); onViewResume(item.resume_id); }}
              className="text-[10px] text-blue-600 hover:text-blue-800 font-medium hover:underline shrink-0"
            >
              View Resume
            </button>
          </div>
          {item.designation && (
            <p className="text-xs text-gray-500 -mt-0.5 italic">{item.designation} · {item.experience_years} yrs exp</p>
          )}
          {!item.designation && item.experience_years > 0 && (
            <p className="text-xs text-gray-500 -mt-0.5 italic">{item.experience_years} yrs experience</p>
          )}
          <div className="flex flex-wrap gap-1 mt-1">
            <Badge label="Skills" value={item.score_breakdown.skills} maxVal={35} />
            <Badge label="Domain" value={item.score_breakdown.domain} maxVal={25} />
            <Badge label="Edu" value={item.score_breakdown.education} maxVal={15} />
            <Badge label="Certs" value={item.score_breakdown.certifications} maxVal={15} />
            <Badge label="Exp" value={item.score_breakdown.experience} maxVal={10} />
          </div>
        </div>
        <div className="text-right shrink-0 w-36">
          <div className={`text-[2rem] font-black leading-none tracking-tighter ${c.text}`}>{finalPct.toFixed(0)}%</div>
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">Match Index</p>
          <div className="text-[9px] font-black text-slate-500 mt-2 flex items-center justify-end gap-1 uppercase tracking-tighter">
            <span className="bg-white px-1.5 py-0.5 rounded border border-slate-200 shadow-sm">ST: {item.structured_score?.toFixed(0) || 0}</span>
            <span className="bg-white px-1.5 py-0.5 rounded border border-slate-200 shadow-sm">AI: {item.llm_score?.toFixed(0) || 0}</span>
          </div>
        </div>
        <svg
          className={`w-6 h-6 text-gray-400 shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {expanded && (
        <div className="px-4 py-4 bg-gray-50 border-t border-gray-100 space-y-4">
          <div className="grid grid-cols-2 gap-8">
            {/* Left: Structured Breakdown */}
            <div>
              <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-3">
                Structured Match ({item.structured_score?.toFixed(0) || 0}/100) — 50% weight
              </h4>
              <div className="space-y-4">
                <ScoreBar score={item.score_breakdown.skills} max={35} label="Skills Match" />
                <ScoreBar score={item.score_breakdown.domain} max={25} label="Domain Expertise" />
                <ScoreBar score={item.score_breakdown.education} max={15} label="Education Match" />
                <ScoreBar score={item.score_breakdown.certifications} max={15} label="Certifications Match" />
                <ScoreBar score={item.score_breakdown.experience} max={10} label="Experience Match" />
              </div>
              <div className="text-[10px] mt-3 font-bold">
                <span className={expMet ? 'text-green-700' : 'text-red-600'}>
                  {item.experience_years} yrs {expMet ? `(\u2713 meets ${reqExp} yr req)` : `(\u2717 below ${reqExp} yr req)`}
                </span>
              </div>
              {(item.matched_skills?.length > 0 || item.missing_skills?.length > 0) && (
                <div className="mt-4 space-y-4">
                  {item.matched_skills?.length > 0 && (
                    <div>
                      <p className="text-[9px] font-black text-emerald-600 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Matched Skills ({item.matched_skills.length})
                      </p>
                      <div className="flex flex-wrap">
                        {item.matched_skills.map((s) => (
                          <SkillTag key={s} skill={s} matched />
                        ))}
                      </div>
                    </div>
                  )}

                  {item.missing_skills?.length > 0 && (
                    <div>
                      <p className="text-[9px] font-black text-rose-600 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> Missing Skills ({item.missing_skills.length})
                      </p>
                      <div className="flex flex-wrap">
                        {item.missing_skills.map((s) => (
                          <SkillTag key={s} skill={s} matched={false} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Right: AI Analysis */}
            <div className="bg-white rounded-2xl border border-slate-100 p-6 shadow-sm relative overflow-hidden">
              <div className="absolute top-0 right-0 p-3 opacity-10">
                <BrainCircuit className="w-12 h-12 text-indigo-600" />
              </div>
              <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-6 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" /> AI JUDGMENT VECTOR ({item.llm_score?.toFixed(0) || 0}/100)
              </h4>
              <div className="mb-8">
                <p className="text-sm text-slate-600 leading-relaxed font-medium italic border-l-4 border-indigo-100 pl-4 py-1">"{item.llm_explanation}"</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                {item.strengths && item.strengths.length > 0 && (
                  <div>
                    <p className="text-[10px] font-black text-green-700 uppercase tracking-widest mb-2 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500" /> Strengths
                    </p>
                    {item.strengths.map((s, i) => (
                      <p key={i} className="text-[11px] text-gray-600 flex items-start gap-1.5 mb-1.5">
                        <span className="text-green-500 font-bold shrink-0">{'\u2713'}</span> {s}
                      </p>
                    ))}
                  </div>
                )}
                {item.concerns && item.concerns.length > 0 && (
                  <div>
                    <p className="text-[10px] font-black text-red-700 uppercase tracking-widest mb-2 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500" /> Concerns
                    </p>
                    {item.concerns.map((c, i) => (
                      <p key={i} className="text-[11px] text-gray-600 flex items-start gap-1.5 mb-1.5">
                        <span className="text-red-500 font-bold shrink-0">{'\u2717'}</span> {c}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="text-[10px] font-black text-gray-400 border-t border-gray-100 pt-3 uppercase tracking-tighter">
            Match Quality Calculation = [0.5 \u00d7 Structured Scorer] + [0.5 \u00d7 AI Reasoning Engine]
          </div>
        </div>
      )}
    </div>
  );
}

function RoleAccordion({ role, onViewResume }: { role: MatchResponse; onViewResume: (id: number) => void }) {
  const [open, setOpen] = useState(false);
  const reqs = role.role_requirements;
  const topScore = role.results.length > 0 ? role.results[0].final_score : 0;
  const topColor = gradeColor(topScore);

  return (
    <div className="bg-white rounded-3xl border border-gray-100 mb-4 overflow-hidden shadow-sm">
      <div
        onClick={() => setOpen(!open)}
        className="flex items-center gap-6 px-6 py-5 cursor-pointer hover:bg-gray-50 transition-all group"
      >
        <div className={`w-1.5 h-12 rounded-full ${topColor.bg} border-l-4 ${topColor.border} transition-all group-hover:scale-y-110`}></div>

        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-black text-gray-900 uppercase tracking-tight">{role.role_title}</h3>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            {reqs && (
              <>
                {reqs.min_experience > 0 && (
                  <span className="text-[10px] font-black text-blue-600 bg-blue-50 px-2 py-0.5 rounded uppercase tracking-widest">
                    {reqs.min_experience}+ yrs exp required
                  </span>
                )}
                {reqs.required_skills.length > 0 && (
                  <span className="text-[10px] font-black text-purple-600 bg-purple-50 px-2 py-0.5 rounded uppercase tracking-widest">
                    {reqs.required_skills.length} core skills
                  </span>
                )}
                {reqs.required_domain.length > 0 && (
                  <span className="text-[10px] font-black text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded uppercase tracking-widest">
                    {reqs.required_domain.join(', ')} sector
                  </span>
                )}
              </>
            )}
          </div>
        </div>

        <div className="text-right shrink-0">
          <div className={`text-2xl font-black ${topColor.text}`}>{topScore.toFixed(0)}%</div>
          <div className="text-[9px] font-black text-gray-400 uppercase tracking-widest">Top Match</div>
        </div>

        <svg
          className={`w-6 h-6 text-gray-400 shrink-0 transition-transform duration-300 ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {open && (
        <div className="px-6 pb-6 pt-2 bg-gray-50/20 border-t border-gray-50">
          {(() => {
            const primary = role.results.filter(r => r.final_score >= 50);
            const secondary = role.results.filter(r => r.final_score < 50);
            return role.results.length === 0 ? (
              <p className="text-sm text-gray-400 italic text-center py-10">No qualifying candidates found for this role criteria.</p>
            ) : (
              <div className="space-y-4 pt-4">
                {primary.length > 0 && (
                  <div>
                    <h4 className="text-[10px] font-black text-green-700 uppercase tracking-widest mb-3 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-green-500 shadow-sm shadow-green-200" /> Strong Matches ({primary.length})
                    </h4>
                    {primary.map((item, idx) => (
                      <CandidateRow
                        key={item.resume_id}
                        item={item}
                        rank={idx + 1}
                        reqExp={reqs?.min_experience ?? 0}
                        onViewResume={onViewResume}
                      />
                    ))}
                  </div>
                )}
                {secondary.length > 0 && (
                  <div className={primary.length > 0 ? 'mt-8 pt-6 border-t border-dashed border-gray-200' : ''}>
                    <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-gray-300" /> Neutral / Weak Matches ({secondary.length})
                    </h4>
                    <div className="opacity-70 grayscale-[0.3]">
                      {secondary.map((item, idx) => (
                        <CandidateRow
                          key={item.resume_id}
                          item={item}
                          rank={primary.length + idx + 1}
                          reqExp={reqs?.min_experience ?? 0}
                          onViewResume={onViewResume}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

export default function Matching() {
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [selectedTenderId, setSelectedTenderId] = useState<number | null>(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('tenderId');
    return id ? Number(id) : null;
  });
  const [results, setResults] = useState<MatchResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [viewResume, setViewResume] = useState<ResumeDetail | null>(null);
  const [loadingResume, setLoadingResume] = useState(false);

  const handleViewResume = async (resumeId: number) => {
    setLoadingResume(true);
    try {
      const detail = await getResume(resumeId);
      setViewResume(detail);
    } catch {
      setError('Failed to load resume details.');
    } finally {
      setLoadingResume(false);
    }
  };

  useEffect(() => {
    listTenders().then(setTenders).catch(() => { });
  }, []);

  useEffect(() => {
    if (!selectedTenderId) { setResults([]); return; }
    getMatchResults(selectedTenderId).then(data => {
      if (data && data.length > 0) setResults(data);
      else setResults([]);
    }).catch(() => { });
  }, [selectedTenderId]);

  const handleRunMatch = async () => {
    if (!selectedTenderId) return;
    setLoading(true);
    setError('');
    setResults([]);
    try {
      const data = await runMatching(selectedTenderId);
      setResults(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'AI Matching engine error.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto">
      <div className="mb-12 text-left animate-in fade-in slide-in-from-left duration-700">
        <h2 className="text-4xl font-black text-slate-900 tracking-tighter flex items-center gap-4 uppercase">
          <span className="w-1.5 h-10 bg-indigo-600 rounded-full shadow-[0_0_15px_rgba(79,70,229,0.3)]" />
          Candidate Matching Audit
        </h2>
        <p className="text-slate-400 mt-3 font-bold uppercase tracking-[0.3em] text-[10px] ml-5">Ranked profiles via structured indices and AI reasoning engine.</p>
      </div>

      {error && (
        <div className="mb-8 p-4 bg-red-50 border border-red-100 rounded-2xl flex items-center justify-between shadow-sm">
          <p className="text-red-700 text-sm font-bold uppercase tracking-tight">{error}</p>
          <button onClick={() => setError('')} className="text-red-400 hover:text-red-600 font-black">✕</button>
        </div>
      )}

      {/* Controls */}
      <div className="bg-white rounded-[32px] border border-gray-100 shadow-2xl p-8 mb-10 overflow-hidden relative">
        <div className="absolute top-0 right-0 w-32 h-32 bg-blue-50/50 rounded-full blur-3xl -mr-16 -mt-16"></div>
        <div className="flex flex-col md:flex-row items-end gap-8 text-left relative z-10">
          <div className="flex-1 w-full">
            <label className="block text-[10px] font-black text-gray-400 uppercase tracking-[0.2em] mb-4">Target Tender Document</label>
            <select
              value={selectedTenderId ?? ''}
              onChange={(e) => {
                setSelectedTenderId(Number(e.target.value) || null);
                setResults([]);
              }}
              className="w-full bg-gray-50 border-2 border-gray-50 rounded-2xl px-5 py-4 text-sm font-bold focus:bg-white focus:border-blue-500 transition-all outline-none appearance-none shadow-inner"
            >
              <option value="">Select a tender to analyze...</option>
              {tenders.map((t) => (
                <option key={t.id} value={t.id}>
                  [TND-{String(t.id).padStart(4, '0')}] {t.project_name} ({t.roles_count} roles specified)
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleRunMatch}
            disabled={!selectedTenderId || loading}
            className="w-full md:w-auto px-10 py-4 bg-blue-600 text-white text-xs font-black uppercase tracking-[0.2em] rounded-2xl hover:bg-black disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-xl shadow-blue-600/20 active:scale-95 flex items-center justify-center gap-3"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                Analyzing...
              </>
            ) : 'RUN AI MATCHING'}
          </button>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="py-24 text-center">
          <div className="w-20 h-20 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-8 shadow-2xl shadow-blue-600/10" />
          <p className="text-gray-400 font-black uppercase tracking-[0.3em] text-[10px] italic">Deep Analysis in progress...</p>
        </div>
      )}

      {/* Results */}
      {!loading && results.length > 0 && (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 px-2">
            <div>
              <h3 className="text-2xl font-black text-gray-900 uppercase tracking-tighter italic">
                {results.length} Manpower Categories
              </h3>
              <p className="text-gray-400 text-xs font-bold uppercase tracking-widest mt-1">Found matching profiles for the following roles</p>
            </div>
          </div>

          <div className="space-y-6">
            {results.map((r) => (
              <RoleAccordion key={r.role_title} role={r} onViewResume={handleViewResume} />
            ))}
          </div>
        </div>
      )}

      {!loading && results.length === 0 && selectedTenderId && !error && (
        <div className="py-24 text-center">
          <div className="w-24 h-24 bg-gray-50 rounded-[32px] flex items-center justify-center mx-auto mb-6 border border-gray-100 shadow-inner">
            <svg className="w-10 h-10 text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.618.309a2 2 0 01-1.789 0l-.618-.309a6 6 0 00-3.86-.517l-2.387.477a2 2 0 00-1.022.547V18a2 2 0 002 2h12a2 2 0 002-2v-2.572zM3.582 15.428a2 2 0 011.022-.547l2.387-.477a6 6 0 013.86.517l.618.309a2 2 0 001.789 0l.618-.309a6 6 0 013.86-.517l2.387.477a2 2 0 011.022.547V10a2 2 0 00-2-2 2 2 0 00-2-2 2 2 0 00-2-2 2 2 0 00-2 2 2 2 0 00-2 2 2 2 0 00-2 2v5.428z" />
            </svg>
          </div>
          <p className="text-gray-400 font-bold uppercase tracking-widest text-[11px] italic">No results stored. Run a new analysis to see matches.</p>
        </div>
      )}

      {/* Detail Slide Panel */}
      {(viewResume || loadingResume) && (
        <div className="fixed inset-0 z-[60] flex justify-end">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm transition-all" onClick={() => setViewResume(null)}></div>
          <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl overflow-y-auto animate-in slide-in-from-right duration-500">
            <div className="sticky top-0 bg-white/80 backdrop-blur-md border-b border-gray-100 p-6 flex items-center justify-between z-10">
              <h3 className="font-black text-xl text-gray-900 uppercase tracking-tighter italic">
                {loadingResume ? 'Authenticating...' : 'Candidate Intelligence'}
              </h3>
              <button
                onClick={() => setViewResume(null)}
                className="w-10 h-10 bg-gray-50 rounded-xl flex items-center justify-center text-gray-400 hover:text-red-500 transition-all font-black text-xl"
              >
                ✕
              </button>
            </div>

            {loadingResume && (
              <div className="flex flex-col items-center justify-center py-40">
                <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mb-6" />
                <p className="text-[10px] font-black text-gray-300 uppercase tracking-[0.3em]">Querying Knowledge Base...</p>
              </div>
            )}

            {viewResume && !loadingResume && (
              <div className="p-8 space-y-10">
                {/* Header Card */}
                <div className="bg-gray-50 rounded-[40px] p-8 flex flex-col md:flex-row items-center gap-8 relative overflow-hidden group">
                  <div className="absolute top-0 right-0 w-40 h-40 bg-white/50 rounded-full blur-3xl -mr-20 -mt-20 group-hover:bg-blue-100/50 transition-all duration-700"></div>

                  <div className="relative z-10 shrink-0">
                    {viewResume.photo_url ? (
                      <img
                        src={viewResume.photo_url}
                        alt={viewResume.name}
                        className="w-24 h-24 rounded-3xl object-cover border-4 border-white shadow-2xl"
                      />
                    ) : (
                      <div className="w-24 h-24 rounded-3xl bg-white flex items-center justify-center text-gray-300 text-3xl font-black shadow-2xl">
                        {viewResume.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                      </div>
                    )}
                  </div>

                  <div className="relative z-10 flex-1 text-center md:text-left">
                    <p className="text-3xl font-black text-gray-900 uppercase tracking-tighter leading-none mb-2">{viewResume.name}</p>
                    <div className="flex flex-wrap justify-center md:justify-start items-center gap-2">
                      <span className="text-[10px] font-black text-blue-600 bg-blue-50 px-3 py-1 rounded-full uppercase tracking-widest">{viewResume.total_years_experience} Years Aggregate EXP</span>
                    </div>
                    <div className="mt-4 flex flex-wrap justify-center md:justify-start gap-4">
                      {viewResume.email && (
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest italic">{viewResume.email}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Content Sections */}
                <div className="grid grid-cols-1 gap-10">
                  {/* Skills Breakdown */}
                  {viewResume.skills.length > 0 && (
                    <section>
                      <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.3em] mb-4 flex items-center gap-3">
                        <span className="w-8 h-[1px] bg-gray-100" /> Technical Arsenal
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {viewResume.skills.map((s, i) => (
                          <span key={i} className="px-4 py-2 text-[11px] font-bold bg-white text-gray-900 rounded-2xl border border-gray-100 shadow-sm hover:border-blue-200 hover:text-blue-600 transition-all cursor-default">
                            {s}
                          </span>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Professional History */}
                  {viewResume.experience.length > 0 && (
                    <section>
                      <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.3em] mb-6 flex items-center gap-3">
                        <span className="w-8 h-[1px] bg-gray-100" /> Professional Chronology
                      </h4>
                      <div className="space-y-6">
                        {viewResume.experience.map((exp, i) => (
                          <div key={i} className="relative pl-8 group">
                            <div className="absolute left-0 top-0 bottom-0 w-1 bg-gray-50 rounded-full group-hover:bg-blue-100 transition-colors"></div>
                            <div className="absolute left-[-4px] top-1 w-3 h-3 rounded-full border-2 border-white bg-gray-200 group-hover:bg-blue-500 transition-colors"></div>

                            <p className="text-sm font-black text-gray-900 uppercase tracking-tight">{exp.role}</p>
                            <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mt-0.5">{exp.company} <span className="text-gray-300 mx-1">/</span> {exp.duration}</p>
                            {exp.description && <p className="text-xs text-gray-500 mt-3 leading-relaxed italic">"{exp.description}"</p>}
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Education & Intel */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                    {viewResume.education.length > 0 && (
                      <section>
                        <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.3em] mb-4">Academic Background</h4>
                        <div className="space-y-3">
                          {viewResume.education.map((edu, i) => (
                            <p key={i} className="text-[11px] font-bold text-gray-700 bg-gray-50 p-3 rounded-2xl border border-gray-100">{edu}</p>
                          ))}
                        </div>
                      </section>
                    )}

                    {viewResume.domain_expertise.length > 0 && (
                      <section>
                        <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.3em] mb-4">Core Domains</h4>
                        <div className="flex flex-wrap gap-2">
                          {viewResume.domain_expertise.map((d, i) => (
                            <span key={i} className="px-3 py-1.5 text-[10px] font-black bg-green-50 text-green-700 rounded-xl border border-green-100 uppercase tracking-tighter italic shadow-sm">{d}</span>
                          ))}
                        </div>
                      </section>
                    )}
                  </div>

                  {/* Certifications */}
                  {viewResume.certifications.length > 0 && (
                    <section>
                      <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-[0.3em] mb-4">Industry Credentials</h4>
                      <div className="flex flex-wrap gap-2">
                        {viewResume.certifications.map((c, i) => (
                          <span key={i} className="px-3 py-1.5 text-[10px] font-black bg-amber-50 text-amber-700 rounded-xl border border-amber-100 uppercase tracking-tight shadow-sm italic">
                            \u2605 {c}
                          </span>
                        ))}
                      </div>
                    </section>
                  )}
                </div>

                {/* Metadata Footer */}
                <div className="pt-10 border-t border-gray-50 flex items-center justify-between text-[9px] font-black text-gray-300 uppercase tracking-[0.2em] italic">
                  <span>Digital Identity: {viewResume.file_name}</span>
                  <span>Processed: {new Date(viewResume.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
