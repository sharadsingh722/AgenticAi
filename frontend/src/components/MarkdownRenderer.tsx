import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
    User,
    GraduationCap,
    Star,
    ChevronRight
} from 'lucide-react';

interface MarkdownRendererProps {
    content: string;
}

export const MarkdownRenderer = ({ content }: MarkdownRendererProps) => {
    return (
        <div className="prose prose-slate prose-sm max-w-none">
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    h1: ({ children }) => (
                        <h1 className="text-xl font-extrabold text-slate-900 mt-6 mb-4 pb-2 border-b border-slate-100 flex items-center gap-2">
                            <Star className="w-5 h-5 text-indigo-500 fill-indigo-100" />
                            {children}
                        </h1>
                    ),
                    h2: ({ children }) => (
                        <h2 className="text-lg font-bold text-slate-800 mt-5 mb-3 flex items-center gap-2">
                            <div className="w-1 h-6 bg-indigo-500 rounded-full" />
                            {children}
                        </h2>
                    ),
                    h3: ({ children }) => (
                        <h3 className="text-md font-semibold text-slate-700 mt-4 mb-2 flex items-center gap-2">
                            <ChevronRight className="w-4 h-4 text-slate-400" />
                            {children}
                        </h3>
                    ),
                    p: ({ children }) => {
                        // Check if this paragraph contains a score or special profile field
                        const text = String(children);
                        if (text.includes('Score:')) {
                            const match = text.match(/Score:\s*([\d.]+)%/);
                            const score = match ? parseFloat(match[1]) : null;
                            const llmMatch = text.match(/\(LLM:\s*([\d.]+)\)/);
                            const llmScore = llmMatch ? parseFloat(llmMatch[1]) : null;

                            return (
                                <div className="bg-indigo-50/50 rounded-xl p-3 my-2 border border-indigo-100/50">
                                    <div className="flex justify-between items-center mb-1.5">
                                        <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider flex items-center gap-1">
                                            <Star className="w-3 h-3" /> System Match Score
                                        </span>
                                        <span className="text-lg font-black text-indigo-700">{score}%</span>
                                    </div>
                                    <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden shadow-inner">
                                        <div
                                            className="h-full bg-gradient-to-r from-indigo-500 to-indigo-600 rounded-full transition-all duration-1000 ease-out shadow-[0_0_10px_rgba(79,70,229,0.3)]"
                                            style={{ width: `${score}%` }}
                                        />
                                    </div>
                                    {llmScore && (
                                        <div className="mt-2 flex items-center gap-2">
                                            <div className="text-[10px] text-slate-500">AI Logic:</div>
                                            <div className="text-[10px] font-bold text-slate-700 px-1.5 py-0.5 bg-white rounded border border-slate-200">{llmScore}/100</div>
                                        </div>
                                    )}
                                </div>
                            );
                        }
                        return <p className="text-slate-600 leading-relaxed mb-3">{children}</p>;
                    },
                    li: ({ children }) => {
                        const text = String(children);

                        // Detect if this is a candidate name entry: "1. **Name**"
                        const nameMatch = text.match(/^(\*\*[^*]+\*\*)/);
                        if (nameMatch) {
                            const name = nameMatch[0].replace(/\*\*/g, '');
                            const rest = text.replace(nameMatch[0], '').trim();

                            return (
                                <li className="list-none mb-10">
                                    <div className="group bg-white rounded-[28px] border border-slate-200 overflow-hidden shadow-[0_4px_30px_rgba(0,0,0,0.02)] hover:shadow-[0_10px_50px_rgba(79,70,229,0.06)] transition-all duration-700">
                                        {/* Header Bar */}
                                        <div className="bg-slate-50/50 px-8 py-5 flex items-center justify-between border-b border-slate-100">
                                            <div className="flex items-center gap-4">
                                                <div className="w-12 h-12 rounded-2xl bg-indigo-600 flex items-center justify-center text-white shadow-lg shadow-indigo-100 group-hover:rotate-6 transition-transform duration-500">
                                                    <User className="w-6 h-6" />
                                                </div>
                                                <div>
                                                    <h4 className="text-xl font-black text-slate-900 tracking-tight leading-none mb-1 uppercase">
                                                        {name}
                                                    </h4>
                                                    <div className="flex gap-2">
                                                        {rest.match(/ID:(\d+)/) && (
                                                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                                                                Candidate ID: {rest.match(/ID:\s*(\d+)/)?.[1]}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="hidden md:block">
                                                <span className="px-3 py-1 bg-white rounded-full border border-slate-200 text-[10px] font-bold text-indigo-500 uppercase tracking-widest shadow-sm">
                                                    Professional Profile
                                                </span>
                                            </div>
                                        </div>

                                        {/* Card Content - The Grid */}
                                        <div className="p-8">
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6">
                                                {/* Role Info */}
                                                {(rest.includes('Role:') || rest.includes('Current Role:')) && (
                                                    <div className="space-y-1">
                                                        <label className="text-[10px] font-bold text-indigo-500 uppercase tracking-[0.15em] block mb-1">Designation</label>
                                                        <p className="text-sm font-bold text-slate-800 tracking-tight leading-snug">
                                                            {rest.match(/(?:Role|Current Role):\s*([^|*\n]+)/)?.[1]?.trim() || 'N/A'}
                                                        </p>
                                                    </div>
                                                )}

                                                {/* Experience Info */}
                                                {(rest.includes('Experience:') || rest.includes('yrs')) && (
                                                    <div className="space-y-1">
                                                        <label className="text-[10px] font-bold text-indigo-500 uppercase tracking-[0.15em] block mb-1">Professional Tenure</label>
                                                        <p className="text-sm font-bold text-slate-800 tracking-tight leading-snug uppercase">
                                                            {rest.match(/(?:Experience:\s*)?([\d.]+)\s*yrs/)?.[1] || rest.match(/Experience:\s*([^|*\n]+)/)?.[1] || 'N/A'} YEARS OF EXPERIENCE
                                                        </p>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Education Section */}
                                            {rest.includes('Education:') && (
                                                <div className="mt-8 pt-6 border-t border-slate-100">
                                                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.15em] block mb-3">Academic Excellence</label>
                                                    <div className="flex items-start gap-3 p-4 bg-slate-50/30 rounded-2xl border border-slate-100">
                                                        <GraduationCap className="w-5 h-5 text-indigo-500 shrink-0 mt-0.5" />
                                                        <p className="text-xs text-slate-600 font-bold leading-relaxed tracking-tight group-hover:text-slate-900 transition-colors">
                                                            {rest.match(/Education:\s*([^|*\n]+)/)?.[1]?.trim() || 'N/A'}
                                                        </p>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Skills Section */}
                                            {rest.includes('Skills:') && (
                                                <div className="mt-6">
                                                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.15em] block mb-3 leading-none">Core Competencies</label>
                                                    <div className="flex flex-wrap gap-2">
                                                        {(rest.match(/Skills:\s*([^|*\n]+)/)?.[1] || '').split(',').map((skill, si) => (
                                                            <span key={si} className="px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-[10px] font-bold text-slate-500 shadow-sm hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50/30 hover:-translate-y-0.5 transition-all cursor-default active:scale-95">
                                                                {skill.trim()}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </li>
                            );
                        }

                        // Suppression logic for sub-items that were parsed into the card
                        if (text.match(/^(Role|Experience|Education|Skills|Current Role|Std-Edu):/)) {
                            return null;
                        }

                        // Clean, high-end bullet for general list items
                        return (
                            <li className="text-slate-600 mb-2 font-medium flex items-start gap-4 list-none group">
                                <div className="mt-2 w-1.5 h-1.5 rounded-full bg-slate-300 group-hover:bg-indigo-500 transition-colors shrink-0" />
                                <span className="text-sm leading-relaxed tracking-tight">{children}</span>
                            </li>
                        );
                    },
                    strong: ({ children }) => <strong className="font-bold text-slate-900">{children}</strong>,
                    code: ({ children }) => (
                        <code className="px-1.5 py-0.5 bg-slate-100 text-indigo-600 font-mono text-[11px] rounded border border-slate-200">
                            {children}
                        </code>
                    ),
                    table: ({ children }) => (
                        <div className="my-6 overflow-x-auto rounded-xl border border-slate-200 bg-white">
                            <table className="min-w-full divide-y divide-slate-200">
                                {children}
                            </table>
                        </div>
                    ),
                    thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,
                    th: ({ children }) => (
                        <th className="px-4 py-3 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                            {children}
                        </th>
                    ),
                    td: ({ children }) => (
                        <td className="px-4 py-3 text-xs text-slate-600 border-t border-slate-100 italic">
                            {children}
                        </td>
                    ),
                }}
            >
                {content}
            </ReactMarkdown>
        </div>
    );
};
