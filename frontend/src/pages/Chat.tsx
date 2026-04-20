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
  Terminal
} from 'lucide-react';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import { cn } from '../utils/utils';

interface ChatMsg {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  thought?: string;
  toolCalls?: { tool: string; input?: any; result?: string; expanded?: boolean }[];
}

export default function Chat() {
  const [messages, setMessages] = useState<ChatMsg[]>(() => {
    const saved = localStorage.getItem('chat_messages');
    return saved ? JSON.parse(saved) : [];
  });
  const [input, setInput] = useState('');
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

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);
    setCurrentTool('');
    let thinkingText = '';

    const toolCalls: { tool: string; input?: any; result?: string }[] = [];

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: userMsg }),
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
              setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: event.content, thought: thinkingText, toolCalls: [...toolCalls] },
              ]);
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

            {messages.map((msg, i) => (
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
                    ) : (
                      <MarkdownRenderer content={msg.content} />
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
            ))}

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
          <div className="w-full max-w-4xl mx-auto">
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
                  onClick={handleSend}
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
