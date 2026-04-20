import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTender } from '../api/client';
import type { TenderDetail } from '../types';

export default function TenderView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [tender, setTender] = useState<TenderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getTender(Number(id))
      .then(setTender)
      .catch(() => setError('Failed to load tender details.'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (error || !tender) {
    return (
      <div className="min-h-screen bg-gray-50 p-8 text-center">
        <div className="max-w-md mx-auto bg-red-50 p-6 rounded-2xl border border-red-100">
          <p className="text-red-600 font-medium mb-4">{error || 'Tender not found'}</p>
          <button 
            onClick={() => navigate('/tenders')}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors"
          >
            Back to List
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white text-gray-900 font-sans selection:bg-blue-100 pb-20">
      {/* Top Banner / Actions */}
      <div className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-gray-100 px-4 md:px-6 py-3 shadow-sm">
        <div className="max-w-7xl mx-auto flex flex-col xs:flex-row items-center justify-between gap-3 md:gap-4">
          <div className="flex items-center gap-2 md:gap-4 min-w-0 w-full xs:w-auto">
            <button 
              onClick={() => navigate(-1)}
              className="p-2 -ml-2 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-900 transition-all shrink-0"
              title="Go Back"
            >
              <svg className="w-5 h-5 md:w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-0.5 overflow-hidden">
                <span className="px-1.5 py-0.5 bg-blue-600 text-white text-[9px] font-black rounded uppercase tracking-tighter shrink-0">
                  TND-{tender.id.toString().padStart(4, '0')}
                </span>
                <h1 className="text-sm md:text-lg font-black text-gray-900 truncate tracking-tight">
                  {tender.project_name}
                </h1>
              </div>
              <p className="text-[8px] md:text-[10px] text-gray-400 font-black uppercase tracking-widest truncate">Tender Dashboard</p>
            </div>
          </div>
          
          <div className="flex items-center gap-2 w-full xs:w-auto justify-end shrink-0">
            <button 
              onClick={() => navigate(`/matching?tenderId=${tender.id}`)}
              className="flex-1 xs:flex-none flex items-center justify-center gap-2 px-3 md:px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] md:text-sm font-bold rounded-xl transition-all shadow-md active:scale-95 whitespace-nowrap"
            >
               <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                </svg>
              <span className="hidden sm:inline">Find Matches</span>
              <span className="sm:hidden">Match</span>
            </button>
            <a 
              href={`/api/tenders/${tender.id}/download`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 px-3 md:px-4 py-2 border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-[11px] md:text-sm font-bold rounded-xl transition-all shadow-sm active:scale-95"
            >
              <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              PDF
            </a>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto p-6 md:p-8 space-y-8">
        {/* Header Summary Section */}
        <section className="relative overflow-hidden bg-white border border-gray-100 rounded-3xl p-8 shadow-xl shadow-gray-200/50">
          <div className="relative z-10">
            <div className="mb-8">
              <div className="flex items-center gap-3 mb-4">
                 <div className="p-2.5 rounded-2xl bg-blue-100 text-blue-600">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                    </svg>
                 </div>
                 <div>
                    <p className="text-[10px] text-blue-600 font-black uppercase tracking-widest mb-1">Project Client</p>
                    <h2 className="text-2xl font-black text-gray-900 tracking-tight">{tender.client || 'Government of India'}</h2>
                 </div>
              </div>
              <h3 className="text-xl font-bold text-gray-600 leading-snug">
                {tender.project_name}
              </h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="p-5 rounded-3xl bg-gray-50 border border-gray-100 group hover:shadow-lg hover:shadow-blue-500/5 transition-all">
                <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-2">Duration</p>
                <div className="flex items-center gap-3">
                   <div className="p-2 rounded-xl bg-blue-100 text-blue-600">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                   </div>
                   <span className="font-black text-gray-800 tracking-tight">{tender.project_duration || 'Not Specified'}</span>
                </div>
              </div>

              <div className="p-5 rounded-3xl bg-gray-50 border border-gray-100 group hover:shadow-lg hover:shadow-indigo-500/5 transition-all">
                <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-2">Document Ref</p>
                <div className="flex items-center gap-3">
                   <div className="p-2 rounded-xl bg-indigo-100 text-indigo-600">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 11h.01M7 15h.01M11 7h.01M11 11h.01M11 15h.01M15 7h.01M15 11h.01M15 15h.01" />
                      </svg>
                   </div>
                   <span className="font-black text-gray-800 tracking-tight font-mono text-sm truncate">{tender.document_reference || 'Ref-0001'}</span>
                </div>
              </div>

              <div className="p-5 rounded-3xl bg-gray-50 border border-gray-100 group hover:shadow-lg hover:shadow-emerald-500/5 transition-all">
                <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-2">Issue Date</p>
                <div className="flex items-center gap-3">
                   <div className="p-2 rounded-xl bg-emerald-100 text-emerald-600">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                   </div>
                   <span className="font-black text-gray-800 tracking-tight">{tender.document_date || 'N/A'}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-blue-100/50 rounded-full blur-[100px]"></div>
          <div className="absolute bottom-0 left-0 -ml-16 -mb-16 w-64 h-64 bg-emerald-100/50 rounded-full blur-[100px]"></div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content Area */}
          <div className="lg:col-span-2 space-y-8">
            {/* Required Personnel / Roles */}
            <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
              <h3 className="text-xl font-black text-gray-900 mb-8 flex items-center gap-3 tracking-tight uppercase">
                <div className="p-2 rounded-xl bg-blue-100 text-blue-600">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                </div>
                Manpower Requirements ({tender.required_roles.length})
              </h3>
              
              <div className="space-y-6">
                {tender.required_roles.length === 0 ? (
                  <div className="p-12 text-center bg-gray-50 rounded-3xl border border-dashed border-gray-200">
                    <p className="text-gray-400 font-bold italic">No automated role requirements extracted.</p>
                  </div>
                ) : (
                  tender.required_roles.map((role, i) => (
                    <div key={i} className="p-6 rounded-3xl bg-gray-50 border border-gray-100 hover:bg-white hover:shadow-xl transition-all group">
                       <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                          <h4 className="text-lg font-black text-gray-900 tracking-tight uppercase group-hover:text-blue-600 transition-colors">
                            {role.role_title}
                          </h4>
                          <span className="px-3 py-1 bg-blue-100 text-blue-600 text-[10px] font-black rounded-full border border-blue-200 uppercase tracking-tighter">
                            Min. {role.min_experience} Years Exp.
                          </span>
                       </div>

                       <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {role.required_skills.length > 0 && (
                            <div>
                               <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-2">Preferred Skills</p>
                               <div className="flex flex-wrap gap-1.5">
                                  {role.required_skills.map((s, j) => (
                                    <span key={j} className="px-2.5 py-1 bg-white text-gray-700 text-[10px] font-bold rounded-lg border border-gray-200 shadow-sm uppercase tracking-wider">
                                      {s}
                                    </span>
                                  ))}
                               </div>
                            </div>
                          )}
                          {role.required_domain.length > 0 && (
                            <div>
                               <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-2">Domain Expertise</p>
                               <div className="flex flex-wrap gap-1.5">
                                  {role.required_domain.map((d, j) => (
                                    <span key={j} className="px-2.5 py-1 bg-emerald-50 text-emerald-700 text-[10px] font-bold rounded-lg border border-emerald-100 uppercase tracking-wider">
                                      {d}
                                    </span>
                                  ))}
                               </div>
                            </div>
                          )}
                       </div>
                       
                       {role.required_certifications.length > 0 && (
                         <div className="mt-4 pt-4 border-t border-gray-200/50">
                            <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-2">Preferred Certifications</p>
                            <div className="flex flex-wrap gap-1.5">
                               {role.required_certifications.map((c, j) => (
                                 <span key={j} className="px-2.5 py-1 bg-amber-50 text-amber-700 text-[10px] font-bold rounded-lg border border-amber-100 uppercase tracking-wider">
                                   {c}
                                 </span>
                               ))}
                            </div>
                         </div>
                       )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Eligibility Criteria */}
            {tender.eligibility_criteria.length > 0 && (
               <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
                  <h3 className="text-xl font-black text-gray-900 mb-6 flex items-center gap-3 tracking-tight uppercase">
                    <div className="p-2 rounded-xl bg-amber-100 text-amber-600">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    Eligibility & Bid Criteria
                  </h3>
                  <div className="space-y-4">
                    {tender.eligibility_criteria.map((criteria, i) => (
                      <div key={i} className="flex gap-4 p-4 rounded-2xl bg-gray-50 border border-gray-100 group hover:bg-white hover:shadow-md transition-all">
                        <div className="p-1 rounded bg-amber-200 text-amber-700 mt-0.5 shrink-0">
                           <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                           </svg>
                        </div>
                        <p className="text-gray-700 leading-relaxed font-medium text-sm italic">{criteria}</p>
                      </div>
                    ))}
                  </div>
               </div>
            )}
          </div>

          {/* Sidebar Area */}
          <div className="space-y-8">
            {/* Quick Stats */}
            <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-3xl p-8 text-white shadow-xl shadow-blue-500/20">
               <div className="flex items-center gap-3 mb-6">
                  <svg className="w-8 h-8 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  <h3 className="text-xl font-black uppercase tracking-tighter">Insights</h3>
               </div>
               <div className="space-y-6">
                  <div>
                     <p className="text-xs font-black text-blue-100 uppercase tracking-widest mb-1">Total Needed</p>
                     <p className="text-3xl font-black">{tender.required_roles.length} Expert Roles</p>
                  </div>
                  <div>
                     <p className="text-xs font-black text-blue-100 uppercase tracking-widest mb-1">Technologies</p>
                     <p className="text-3xl font-black">{tender.key_technologies.length} Stack Fields</p>
                  </div>
                  <button 
                    onClick={() => navigate(`/matching?tenderId=${tender.id}`)}
                    className="w-full py-4 bg-white text-blue-600 rounded-2xl font-black uppercase tracking-widest shadow-lg hover:shadow-white/10 active:scale-95 transition-all"
                  >
                    Launch Matcher
                  </button>
               </div>
            </div>

            {/* Key Technologies */}
            <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
              <h3 className="text-xl font-black text-gray-900 mb-6 flex items-center gap-3 tracking-tight uppercase">
                <div className="p-2 rounded-xl bg-purple-100 text-purple-600">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                  </svg>
                </div>
                Key Technologies
              </h3>
              <div className="flex flex-wrap gap-2">
                {tender.key_technologies.map((tech, i) => (
                  <span 
                    key={i} 
                    className="px-4 py-2 bg-gray-50 text-gray-700 text-[10px] font-black uppercase rounded-xl border border-gray-200 shadow-sm tracking-widest"
                  >
                    {tech}
                  </span>
                ))}
              </div>
            </div>

            {/* Document Metadata */}
            <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
               <h3 className="text-sm font-black text-gray-900 mb-4 flex items-center gap-2 uppercase tracking-tight">
                  <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Source Info
               </h3>
               <div className="space-y-3 text-[10px] text-gray-400 font-mono uppercase tracking-widest italic leading-relaxed">
                  <div className="flex justify-between border-b border-gray-50 pb-2">
                    <span>Parsed Status</span>
                    <span className={`font-black ${tender.parse_status === 'success' ? 'text-emerald-500' : 'text-red-500'}`}>{tender.parse_status}</span>
                  </div>
                  <div className="flex justify-between border-b border-gray-50 pb-2">
                    <span>System ID</span>
                    <span className="text-gray-700">{tender.id.toString().padStart(6, '0')}</span>
                  </div>
                  <div className="flex justify-between border-b border-gray-50 pb-2">
                    <span>File Ref</span>
                    <span className="text-gray-700 truncate ml-4" title={tender.file_name}>{tender.file_name}</span>
                  </div>
                  <div className="flex justify-between pt-1">
                    <span>Added At</span>
                    <span className="text-gray-700">{new Date(tender.created_at).toLocaleDateString()}</span>
                  </div>
               </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
