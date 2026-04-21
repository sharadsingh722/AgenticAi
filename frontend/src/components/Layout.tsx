import { useState, useEffect } from 'react';
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import { 
  Users, 
  FileText, 
  Crosshair, 
  Plus, 
  Menu, 
  MessageSquareQuote,
  Settings,
  Circle,
  Trash2
} from 'lucide-react';
import { cn } from '../utils/utils';
import { listSessions, deleteSession } from '../api/client';
import type { ChatSession } from '../api/client';

const navItems = [
  { to: '/resumes', label: 'Resumes', icon: Users },
  { to: '/tenders', label: 'Tenders', icon: FileText },
  { to: '/matching', label: 'Matching', icon: Crosshair },
];

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { sessionId: currentSessionId } = useParams();
  const isChat = location.pathname.startsWith('/chat');
  
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  const closeSidebar = () => setIsSidebarOpen(false);
  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

  useEffect(() => {
    fetchSessions();
  }, [location.pathname]); // Refresh when navigating to/from chat

  const fetchSessions = async () => {
    try {
      const data = await listSessions();
      setSessions(data);
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this chat session?')) {
      try {
        await deleteSession(id);
        setSessions(prev => prev.filter(s => s.id !== id));
        if (currentSessionId === id) {
          navigate('/chat');
        }
      } catch (error) {
        console.error('Failed to delete session:', error);
      }
    }
  };

  const startNewChat = () => {
    const newId = crypto.randomUUID();
    navigate(`/chat/${newId}`);
    closeSidebar();
  };

  const groupSessions = () => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const sevenDaysAgo = new Date(today);
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const grouped: { group: string; items: ChatSession[] }[] = [
      { group: 'Today', items: [] },
      { group: 'Yesterday', items: [] },
      { group: 'Previous 7 Days', items: [] },
    ];

    sessions.forEach(session => {
      const date = new Date(session.updated_at);
      if (date >= today) {
        grouped[0].items.push(session);
      } else if (date >= yesterday) {
        grouped[1].items.push(session);
      } else if (date >= sevenDaysAgo) {
        grouped[2].items.push(session);
      }
    });

    return grouped.filter(g => g.items.length > 0);
  };

  return (
    <div className="min-h-screen bg-white text-slate-900 flex font-sans">
      {/* Mobile Backdrop */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-900/20 z-40 lg:hidden backdrop-blur-sm transition-opacity"
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar */}
      <aside className={cn(
        "fixed inset-y-0 left-0 z-50 w-[280px] bg-slate-50 border-r border-slate-200 flex flex-col transform transition-all duration-300 ease-in-out lg:translate-x-0 lg:static lg:block",
        isSidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        {/* Sidebar Logo */}
        <div className="p-6 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-600 flex items-center justify-center shadow-lg shadow-violet-100">
            <Crosshair className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-[17px] font-black text-slate-900 tracking-tight leading-none">Matcher V2</h2>
            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-[0.15em] mt-1 text-blue-600">Agentic Engine</p>
          </div>
        </div>

        {/* Global Navigation */}
        <nav className="px-3 space-y-1 mb-8">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={closeSidebar}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-4 py-2.5 rounded-xl text-xs font-bold transition-all group",
                  isActive
                    ? "bg-slate-100 text-slate-900 shadow-sm"
                    : "text-slate-500 hover:bg-slate-100/50 hover:text-slate-900"
                )
              }
            >
              <item.icon className="w-4 h-4 transition-colors" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Action Section */}
        <div className="px-4 mb-8">
          <button 
            onClick={startNewChat}
            className={cn(
              "w-full flex items-center gap-3 px-5 py-3.5 rounded-xl text-sm font-black transition-all shadow-lg active:scale-95 group",
              !currentSessionId && isChat
                ? "bg-violet-600 text-white shadow-violet-200" 
                : "bg-white text-slate-900 shadow-sm border border-slate-200 hover:bg-slate-50"
            )}
          >
            <Plus className="w-5 h-5" />
            New Chat
          </button>
        </div>

        {/* History Sections */}
        <div className="flex-1 overflow-y-auto px-3 custom-scrollbar space-y-6 pb-6">
          {groupSessions().map((group) => (
            <div key={group.group}>
              <h3 className="px-4 text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">{group.group}</h3>
              <div className="space-y-0.5">
                {group.items.map((session) => (
                  <NavLink
                    key={session.id}
                    to={`/chat/${session.id}`}
                    onClick={closeSidebar}
                    className={({ isActive }) => cn(
                      "w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-[12px] font-medium transition-all group relative overflow-hidden",
                      isActive
                        ? "bg-slate-200 text-slate-900"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    )}
                  >
                    <MessageSquareQuote className="w-3.5 h-3.5 text-slate-300 group-hover:text-slate-500 shrink-0" />
                    <span className="truncate flex-1">{session.title}</span>
                    <button
                      onClick={(e) => handleDeleteSession(e, session.id)}
                      className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-500 transition-opacity"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </div>

      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Mobile/Floating Header */}
        <header className="lg:hidden p-4 sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white/80 backdrop-blur-xl">
          <button onClick={toggleSidebar} className="p-2 text-slate-500 hover:text-slate-900">
            <Menu className="w-6 h-6" />
          </button>
          <div className="flex items-center gap-2">
            <Circle className="w-2 h-2 text-violet-500 fill-violet-500" />
            <h2 className="text-[13px] font-black text-slate-900 uppercase tracking-tighter">
              Matcher Intelligence
            </h2>
          </div>
          <div className="w-10"></div>
        </header>

        <main className={cn(
          "flex-1 overflow-auto bg-white",
          isChat ? "p-0" : "p-4 md:p-10"
        )}>
          <div className={cn(!isChat && "max-w-7xl mx-auto")}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
