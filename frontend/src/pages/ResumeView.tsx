import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getResume } from '../api/client';
import type { ResumeDetail } from '../types';

export default function ResumeView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [resume, setResume] = useState<ResumeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getResume(Number(id))
      .then(setResume)
      .catch(() => setError('Failed to load resume details.'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (error || !resume) {
    return (
      <div className="min-h-screen bg-gray-50 p-8 text-center">
        <div className="max-w-md mx-auto bg-red-50 p-6 rounded-2xl border border-red-100">
          <p className="text-red-600 font-medium mb-4">{error || 'Resume not found'}</p>
          <button 
            onClick={() => navigate('/resumes')}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors"
          >
            Back to List
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white text-gray-900 font-sans selection:bg-blue-100">
      {/* Top Banner / Actions */}
      <div className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-gray-100 px-6 py-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate(-1)}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-900 transition-all"
            title="Go Back"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {resume.name}
            </h1>
            <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest">Candidate Profile</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <a 
            href={`/api/resumes/${resume.id}/download`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl transition-all shadow-md active:scale-95"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download PDF
          </a>
        </div>
      </div>

      <div className="max-w-6xl mx-auto p-6 md:p-8 space-y-8">
        {/* Header Section */}
        <section className="relative overflow-hidden bg-white border border-gray-100 rounded-3xl p-8 shadow-xl shadow-gray-200/50">
          <div className="relative z-10 flex flex-col md:flex-row items-center md:items-start gap-8">
            <div className="relative">
              {resume.photo_url ? (
                <img 
                  src={resume.photo_url} 
                  alt={resume.name}
                  className="w-32 h-32 md:w-40 md:h-40 rounded-2xl object-cover ring-4 ring-gray-50 shadow-lg"
                />
              ) : (
                <div className="w-32 h-32 md:w-40 md:h-40 rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-4xl font-bold text-white shadow-lg">
                  {resume.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                </div>
              )}
              <div className="absolute -bottom-2 -right-2 px-3 py-1 bg-green-500 text-white text-[10px] font-black uppercase tracking-tighter rounded-md shadow-md border-2 border-white">
                Verified
              </div>
            </div>

            <div className="flex-1 text-center md:text-left">
              <div className="flex flex-wrap items-center justify-center md:justify-start gap-3 mb-2">
                <h2 className="text-3xl font-black text-gray-900">{resume.name}</h2>
                <span className="px-3 py-1 bg-blue-50 text-blue-600 text-xs font-black rounded-full border border-blue-100 uppercase tracking-tighter">
                  {resume.total_years_experience} Yrs Experience
                </span>
              </div>
              <p className="text-gray-600 text-lg mb-6 max-w-2xl font-medium leading-tight">
                {resume.experience.length > 0 ? resume.experience[0].role : 'Professional'}
                {resume.experience.length > 0 && ` at ${resume.experience[0].company}`}
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex items-center gap-3 p-3 rounded-2xl bg-gray-50 border border-gray-100">
                  <div className="p-2 rounded-xl bg-blue-100 text-blue-600">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <span className="text-sm font-medium text-gray-700 truncate">{resume.email || 'N/A'}</span>
                </div>
                <div className="flex items-center gap-3 p-3 rounded-2xl bg-gray-50 border border-gray-100">
                  <div className="p-2 rounded-xl bg-indigo-100 text-indigo-600">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5.25v13.5A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V5.25A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25z" />
                    </svg>
                  </div>
                  <span className="text-sm font-medium text-gray-700">{resume.phone || 'N/A'}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 text-left">
          {/* Main Content Area */}
          <div className="lg:col-span-2 space-y-8">
            {/* Experience */}
            <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
              <h3 className="text-xl font-black text-gray-900 mb-8 flex items-center gap-3 uppercase tracking-tight">
                <div className="p-2 rounded-xl bg-orange-100 text-orange-600">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </div>
                Professional Experience
              </h3>
              
              <div className="space-y-12">
                {resume.experience.map((exp, i) => (
                  <div key={i} className="relative pl-8 group">
                    {/* Timeline Line */}
                    {i !== resume.experience.length - 1 && (
                      <div className="absolute top-8 left-[7px] bottom-[-24px] w-[2px] bg-gray-100"></div>
                    )}
                    {/* Timeline Dot */}
                    <div className="absolute top-2 left-0 w-4 h-4 rounded-full bg-orange-500 ring-4 ring-orange-50 group-hover:scale-125 transition-transform"></div>
                    
                    <div>
                      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                        <h4 className="text-lg font-black text-gray-900 tracking-tight">{exp.role}</h4>
                        <span className="px-3 py-1 bg-gray-100 rounded-full text-[10px] font-black text-gray-400 border border-gray-200 uppercase tracking-widest">
                          {exp.duration}
                        </span>
                      </div>
                      <p className="text-orange-600 font-black text-xs mb-4 uppercase tracking-wider">{exp.company}</p>
                      {exp.description && (
                        <p className="text-gray-600 text-sm leading-relaxed whitespace-pre-wrap italic">
                          {exp.description}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Education */}
            <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
              <h3 className="text-xl font-black text-gray-900 mb-6 flex items-center gap-3 uppercase tracking-tight">
                <div className="p-2 rounded-xl bg-purple-100 text-purple-600">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 14l9-5-9-5-9 5 9 5z" />
                  </svg>
                </div>
                Academic Background
              </h3>
              <div className="space-y-4">
                {resume.education.map((edu, i) => (
                  <div key={i} className="flex gap-4 p-4 rounded-2xl bg-gray-50 border border-gray-100 group hover:bg-white hover:shadow-md transition-all">
                    <div className="w-2 h-2 mt-2 rounded-full bg-purple-500 shrink-0"></div>
                    <p className="text-gray-700 leading-relaxed font-medium text-sm italic">{edu}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Sidebar Area */}
          <div className="space-y-8">
            {/* Skills */}
            <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
              <h3 className="text-xl font-black text-gray-900 mb-6 flex items-center gap-3 uppercase tracking-tight">
                <div className="p-2 rounded-xl bg-green-100 text-green-600">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M12 7a5 5 0 015 5 5 5 0 01-5 5 5 5 0 01-5-5 5 5 0 015-5z" />
                  </svg>
                </div>
                Core Skills
              </h3>
              <div className="flex flex-wrap gap-2">
                {resume.skills.map((skill, i) => (
                  <span 
                    key={i} 
                    className="px-4 py-2 bg-gray-50 text-gray-700 text-[10px] font-black uppercase rounded-xl border border-gray-200 shadow-sm tracking-widest"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>

            {/* Domain Expertise */}
            <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
              <h3 className="text-xl font-black text-gray-900 mb-6 flex items-center gap-3 uppercase tracking-tight">
                <div className="p-2 rounded-xl bg-pink-100 text-pink-600">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945" />
                  </svg>
                </div>
                Industries & Domains
              </h3>
              <div className="space-y-2">
                {resume.domain_expertise.map((domain, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3 rounded-2xl bg-gray-50 border border-gray-200 text-gray-600 text-xs font-black uppercase tracking-widest">
                    <span className="w-1.5 h-1.5 rounded-full bg-pink-500"></span>
                    {domain}
                  </div>
                ))}
              </div>
            </div>

            {/* Certifications */}
            {resume.certifications.length > 0 && (
              <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
                <h3 className="text-xl font-black text-gray-900 mb-6 flex items-center gap-3 uppercase tracking-tight">
                  <div className="p-2 rounded-xl bg-yellow-100 text-yellow-600">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4" />
                    </svg>
                  </div>
                   Certifications
                </h3>
                <div className="space-y-3">
                  {resume.certifications.map((cert, i) => (
                    <div key={i} className="p-4 rounded-2xl bg-yellow-50 border border-yellow-100 text-yellow-800 text-[10px] font-black leading-relaxed uppercase tracking-widest shadow-sm">
                      {cert}
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Metadata */}
            <div className="text-[10px] text-gray-400 font-mono flex flex-col gap-1 italic uppercase tracking-widest">
              <p>System ID: {resume.id.toString().padStart(6, '0')}</p>
              <p>Processed: {new Date(resume.created_at).toLocaleString()}</p>
              <p>Source Ref: {resume.file_name}</p>
            </div>
          </div>
        </div>

        {/* View JSON Block (Full Width Area) */}
        <div className="bg-slate-900 rounded-3xl p-8 shadow-xl mt-12 border border-slate-800">
          <div className="flex items-center gap-3 mb-6">
            <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
            <h3 className="text-sm font-black text-green-400 uppercase tracking-tighter">Raw JSON Payload</h3>
          </div>
          <pre className="text-xs font-mono text-green-300 w-full overflow-auto max-h-[600px] scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-800 p-4 bg-slate-950 rounded-2xl shadow-inner">
            {JSON.stringify((resume as any), null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
