import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { listResumes, deleteResume, uploadResumesBatch } from '../api/client';
import type { Resume } from '../types';

// Inline UploadModal component to ensure robustness and fix the import error
function UploadModal({ onSuccess }: { onSuccess: () => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setError('');
    try {
      await uploadResumesBatch(files);
      setFiles([]);
      setIsOpen(false);
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <button 
        onClick={() => setIsOpen(true)}
        className="px-6 py-2.5 bg-blue-600 text-white text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-blue-700 transition-all shadow-lg shadow-blue-900/10 active:scale-95 flex items-center gap-2"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Upload Resumes
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0f172a]/80 backdrop-blur-sm">
          <div className="bg-white rounded-3xl w-full max-w-md shadow-2xl border border-gray-100 p-8">
            <h3 className="text-xl font-bold text-gray-900 mb-2">Upload Resumes</h3>
            <p className="text-sm text-gray-500 mb-6">Select one or more PDF files to parse</p>

            {error && (
              <div className="mb-4 p-3 bg-red-50 text-red-600 text-xs font-bold rounded-xl border border-red-100">
                {error}
              </div>
            )}

            <input 
              type="file" 
              multiple 
              accept=".pdf"
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
              className="w-full text-sm text-gray-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-black file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 transition-all mb-8"
            />

            <div className="flex gap-3">
              <button 
                onClick={() => setIsOpen(false)}
                className="flex-1 py-3 text-sm font-black text-gray-400 uppercase tracking-widest hover:text-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={handleUpload}
                disabled={uploading || files.length === 0}
                className="flex-3 px-8 py-3 bg-blue-600 text-white text-sm font-black uppercase tracking-widest rounded-2xl hover:bg-blue-700 disabled:opacity-30 transition-all shadow-lg shadow-blue-900/10"
              >
                {uploading ? 'Processing...' : 'Start Upload'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default function Resumes() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const navigate = useNavigate();

  const handleViewResume = (resumeId: number) => {
    navigate(`/resumes/${resumeId}`);
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this resume?')) return;
    try {
      await deleteResume(id);
      setResumes(resumes.filter(r => r.id !== id));
    } catch {
      alert('Failed to delete resume');
    }
  };

  useEffect(() => {
    listResumes().then(setResumes).catch(() => {});
  }, []);

  const handleUploadSuccess = () => {
    listResumes().then(setResumes);
  };

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto text-left">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-gray-900 tracking-tight">Resumes</h2>
          <p className="text-gray-500 mt-1 italic">Manage and view candidate profiles</p>
        </div>
        <UploadModal onSuccess={handleUploadSuccess} />
      </div>

      <div className="bg-white rounded-3xl border border-gray-100 shadow-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-50/50 border-b border-gray-100">
                <th className="px-8 py-5 text-[11px] font-black text-gray-400 uppercase tracking-widest">Candidate</th>
                <th className="px-8 py-5 text-[11px] font-black text-gray-400 uppercase tracking-widest">Contact</th>
                <th className="px-8 py-5 text-[11px] font-black text-gray-400 uppercase tracking-widest">Experience</th>
                <th className="px-8 py-5 text-[11px] font-black text-gray-400 uppercase tracking-widest">Status</th>
                <th className="px-8 py-5 text-[11px] font-black text-gray-400 uppercase tracking-widest text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {resumes.map((resume) => (
                <tr 
                  key={resume.id} 
                  className="group hover:bg-blue-50/30 transition-all cursor-pointer"
                  onClick={() => handleViewResume(resume.id)}
                >
                  <td className="px-8 py-6">
                    <div className="flex items-center gap-4">
                      <div className="relative">
                        {resume.photo_url ? (
                          <img 
                            src={resume.photo_url} 
                            alt={resume.name} 
                            className="w-12 h-12 rounded-2xl object-cover ring-2 ring-white shadow-md group-hover:scale-110 transition-transform"
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-sm font-black shadow-md">
                            {resume.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                          </div>
                        )}
                        <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-green-500 border-2 border-white rounded-full"></div>
                      </div>
                      <div>
                        <p className="text-sm font-bold text-gray-900 group-hover:text-blue-600 transition-colors uppercase tracking-tight">{resume.name}</p>
                        <p className="text-[10px] text-gray-400 font-mono mt-0.5">{resume.file_name.slice(0, 30)}{resume.file_name.length > 30 ? '...' : ''}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-8 py-6">
                    <p className="text-sm font-medium text-gray-600">{resume.email || 'N/A'}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{resume.phone || 'N/A'}</p>
                  </td>
                  <td className="px-8 py-6">
                    <div className="flex flex-col gap-1">
                      <span className="text-sm font-black text-gray-900">{resume.total_years_experience} YRS</span>
                      <div className="flex flex-wrap gap-1">
                        {resume.skills.slice(0, 2).map((skill, i) => (
                          <span key={i} className="px-2 py-0.5 bg-gray-100 text-gray-500 text-[9px] font-black uppercase rounded tracking-tighter">
                            {skill}
                          </span>
                        ))}
                      </div>
                    </div>
                  </td>
                  <td className="px-8 py-6">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-tighter ${
                      resume.parse_status === 'success' 
                        ? 'bg-green-100 text-green-700 border border-green-200' 
                        : 'bg-red-100 text-red-700 border border-red-200'
                    }`}>
                      {resume.parse_status}
                    </span>
                  </td>
                  <td className="px-8 py-6 text-right">
                    <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button 
                        onClick={(e) => { e.stopPropagation(); handleViewResume(resume.id); }}
                        className="p-2 bg-white text-blue-600 border border-blue-100 rounded-xl hover:bg-blue-600 hover:text-white transition-all shadow-sm"
                        title="View Full Details"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        </svg>
                      </button>
                      <button 
                        onClick={(e) => { e.stopPropagation(); handleDelete(resume.id); }}
                        className="p-2 bg-white text-red-500 border border-red-100 rounded-xl hover:bg-red-500 hover:text-white transition-all shadow-sm"
                        title="Delete Resume"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {resumes.length === 0 && (
            <div className="py-32 text-center">
              <div className="w-20 h-20 bg-gray-50 rounded-full flex items-center justify-center mx-auto mb-4 border border-gray-100">
                <svg className="w-10 h-10 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-gray-400 font-bold uppercase tracking-widest text-sm italic">Engine is idle. Upload a resume.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
