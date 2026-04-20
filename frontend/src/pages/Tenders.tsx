import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { listTenders, deleteTender } from '../api/client';
import type { Tender } from '../types';
import SmartUpload from '../components/SmartUpload';

export default function Tenders() {
  const navigate = useNavigate();
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchTenders = async () => {
    if (tenders.length === 0) setLoading(true);
    try {
      setTenders(await listTenders());
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tenders');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTenders();
  }, []);

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this tender?')) return;
    try {
      await deleteTender(id);
      await fetchTenders();
    } catch (err: any) {
      setError('Delete failed');
    }
  };

  return (
    <div className="max-w-6xl mx-auto pb-12">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-black text-gray-900 tracking-tight uppercase">Tenders / RFPs</h2>
          <p className="text-sm text-gray-500 mt-1 font-medium">{tenders.length} Active documents ready for matching</p>
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 text-red-700 rounded-2xl text-sm font-medium border border-red-100 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="p-1 hover:bg-red-100 rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      )}

      <div className="bg-white rounded-[32px] border border-gray-100 p-2 shadow-sm mb-8">
         <SmartUpload onComplete={fetchTenders} />
      </div>

      {/* Tender List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-1 gap-6">
        {loading ? (
          <div className="col-span-full py-20 flex flex-col items-center gap-4">
             <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
             <p className="text-gray-400 font-black uppercase tracking-widest text-xs">Scanning Database...</p>
          </div>
        ) : tenders.length === 0 ? (
          <div className="col-span-full py-20 text-center bg-gray-50 rounded-[40px] border border-dashed border-gray-200">
            <p className="text-gray-400 font-bold italic">No tenders uploaded yet. Use the portal above to add RFPs.</p>
          </div>
        ) : (
          tenders.map((tender) => (
            <div
              key={tender.id}
              onClick={() => navigate(`/tenders/${tender.id}`)}
              className="bg-white rounded-[28px] border border-gray-100 p-6 cursor-pointer hover:shadow-2xl hover:shadow-gray-200/50 hover:border-blue-100 transition-all group relative overflow-hidden"
            >
              <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 relative z-10">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center flex-wrap gap-3 mb-3">
                    <span className="inline-flex items-center px-2 py-1 text-[10px] font-black bg-blue-600 text-white rounded uppercase tracking-tighter">
                      TND-{String(tender.id).padStart(4, '0')}
                    </span>
                    {tender.document_reference && (
                      <span className="inline-flex items-center px-2 py-1 text-[10px] font-black bg-emerald-50 text-emerald-700 border border-emerald-100 rounded uppercase tracking-tighter">
                        Ref: {tender.document_reference}
                      </span>
                    )}
                    <span className="text-[10px] text-gray-400 font-mono italic truncate max-w-[200px]">{tender.file_name}</span>
                  </div>
                  
                  <h3 className="text-xl font-black text-gray-900 group-hover:text-blue-600 transition-colors tracking-tight mb-2">
                    {tender.project_name}
                  </h3>
                  
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs font-bold text-gray-500">
                    <div className="flex items-center gap-1.5">
                       <span className="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
                       {tender.client || 'Government Client'}
                    </div>
                    <div className="flex items-center gap-1.5">
                       <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
                       {tender.roles_count > 0 ? (
                         <span className="text-indigo-600">{tender.roles_count} Roles Extracted</span>
                       ) : (
                         <span className="text-amber-500 italic font-medium">Extracting Requirements...</span>
                       )}
                    </div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-widest bg-gray-50 px-2 py-0.5 rounded-md">
                       Uploaded {new Date(tender.created_at).toLocaleDateString()}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-1.5 mt-4">
                    {tender.key_technologies.slice(0, 5).map((tech, i) => (
                      <span key={i} className="px-3 py-1 text-[10px] font-black bg-gray-50 text-gray-500 rounded-lg border border-gray-100 group-hover:border-blue-100 uppercase tracking-wider">
                        {tech}
                      </span>
                    ))}
                    {tender.key_technologies.length > 5 && (
                       <span className="px-3 py-1 text-[10px] font-black bg-gray-50 text-gray-400 rounded-lg italic">+{tender.key_technologies.length - 5} more</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0 self-end lg:self-center">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/matching?tenderId=${tender.id}`);
                    }}
                    className="px-6 py-3 text-xs font-black bg-gray-900 text-white rounded-2xl hover:bg-blue-600 hover:shadow-lg hover:shadow-blue-500/20 transition-all flex items-center gap-2 uppercase tracking-widest"
                  >
                    Launch Matcher
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(tender.id);
                    }}
                    className="w-12 h-12 flex items-center justify-center rounded-2xl bg-gray-50 text-gray-400 hover:bg-red-50 hover:text-red-500 transition-all border border-gray-100 hover:border-red-100"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="absolute top-0 right-0 -mr-8 -mt-8 w-24 h-24 bg-blue-500/5 rounded-full blur-2xl group-hover:bg-blue-500/10 transition-colors"></div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
