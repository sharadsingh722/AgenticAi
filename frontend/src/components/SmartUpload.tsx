import { useCallback, useState, useRef } from 'react';
import { smartUpload, type SmartUploadEvent } from '../api/client';

interface SmartUploadProps {
  onComplete: () => void;
}

interface FileStatus {
  file: File;
  status: 'pending' | 'processing' | 'done' | 'error' | 'duplicate';
  step: string;
  message: string;
  result?: SmartUploadEvent;
  error?: string;
}

export default function SmartUpload({ onComplete }: SmartUploadProps) {
  const [files, setFiles] = useState<FileStatus[]>([]);
  const [processing, setProcessing] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const processFiles = useCallback(async (fileList: File[]) => {
    const pdfs = fileList.filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfs.length === 0) return;

    const statuses: FileStatus[] = pdfs.map(f => ({
      file: f,
      status: 'pending' as const,
      step: '',
      message: 'Waiting...',
    }));
    setFiles(statuses);
    setProcessing(true);

    // Process files sequentially
    for (let i = 0; i < statuses.length; i++) {
      setFiles(prev => prev.map((f, idx) =>
        idx === i ? { ...f, status: 'processing', step: 'extracting', message: 'Starting...' } : f
      ));

      try {
        await smartUpload(statuses[i].file, (event) => {
          if (event.event === 'progress') {
            setFiles(prev => prev.map((f, idx) =>
              idx === i ? { ...f, step: event.step || '', message: event.message || '' } : f
            ));
          } else if (event.event === 'complete') {
            const isDuplicate = event.parse_status === 'duplicate';
            setFiles(prev => prev.map((f, idx) =>
              idx === i ? {
                ...f,
                status: isDuplicate ? 'duplicate' : 'done',
                result: event,
                message: isDuplicate ? 'Duplicate — already exists' : 'Done',
              } : f
            ));
            onComplete();
          } else if (event.event === 'error') {
            setFiles(prev => prev.map((f, idx) =>
              idx === i ? { ...f, status: 'error', error: event.message } : f
            ));
          }
        });
      } catch (err: any) {
        setFiles(prev => prev.map((f, idx) =>
          idx === i ? { ...f, status: 'error', error: err.message } : f
        ));
      }
    }

    setProcessing(false);
  }, [onComplete]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    processFiles(Array.from(e.dataTransfer.files));
  }, [processFiles]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    processFiles(Array.from(e.target.files || []));
    if (inputRef.current) inputRef.current.value = '';
  };

  const reset = () => {
    setFiles([]);
  };

  const hasResults = files.length > 0;
  const allDone = files.length > 0 && files.every(f => f.status !== 'pending' && f.status !== 'processing');

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Upload area — always show unless actively processing */}
      {!processing && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`p-6 text-center cursor-pointer transition-all border-2 border-dashed rounded-xl m-1 ${
            dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-400 hover:bg-gray-50'
          }`}
        >
          <input ref={inputRef} type="file" accept=".pdf" multiple onChange={handleChange} className="hidden" />
          <div className="flex flex-col items-center gap-1.5">
            <svg className="w-8 h-8 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-sm font-medium text-gray-700">Upload PDF Documents</p>
            <p className="text-xs text-gray-400">
              Drop one or multiple PDFs — resumes and tenders are auto-detected
            </p>
          </div>
        </div>
      )}

      {/* File processing list */}
      {hasResults && (
        <div className="divide-y divide-gray-100">
          {files.map((f, i) => (
            <div key={i} className="px-4 py-3 flex items-center gap-3">
              {/* Status icon */}
              {f.status === 'pending' && (
                <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
                  <span className="text-xs text-gray-400">{i + 1}</span>
                </div>
              )}
              {f.status === 'processing' && (
                <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />
              )}
              {f.status === 'done' && (
                <div className="w-6 h-6 rounded-full bg-green-100 flex items-center justify-center shrink-0">
                  <svg className="w-4 h-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              )}
              {f.status === 'duplicate' && (
                <div className="w-6 h-6 rounded-full bg-yellow-100 flex items-center justify-center shrink-0">
                  <span className="text-xs text-yellow-600">!</span>
                </div>
              )}
              {f.status === 'error' && (
                <div className="w-6 h-6 rounded-full bg-red-100 flex items-center justify-center shrink-0">
                  <svg className="w-4 h-4 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </div>
              )}

              {/* File info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{f.file.name}</p>
                <p className={`text-xs truncate ${
                  f.status === 'done' ? 'text-green-600' :
                  f.status === 'duplicate' ? 'text-yellow-600' :
                  f.status === 'error' ? 'text-red-600' :
                  f.status === 'processing' ? 'text-blue-600' :
                  'text-gray-400'
                }`}>
                  {f.status === 'done' && f.result?.type === 'resume' && `Resume: ${f.result.name} · ${f.result.skills_count} skills · ${f.result.experience_years} yrs`}
                  {f.status === 'done' && f.result?.type === 'tender' && `Tender: ${f.result.project_name} · ${f.result.roles_count} roles`}
                  {f.status === 'done' && f.result?.type && !['resume', 'tender'].includes(f.result.type) && `${f.result.type}: ${f.result.message || 'Not a resume or tender'}`}
                  {f.status === 'duplicate' && 'Skipped — duplicate already exists'}
                  {f.status === 'error' && (f.error || 'Upload failed')}
                  {f.status === 'processing' && f.message}
                  {f.status === 'pending' && 'Waiting...'}
                </p>
              </div>

              {/* Size */}
              <span className="text-[10px] text-gray-400 shrink-0">
                {(f.file.size / 1024).toFixed(0)} KB
              </span>
            </div>
          ))}

          {/* Clear button */}
          {allDone && (
            <div className="px-4 py-2 bg-gray-50 text-right">
              <button onClick={reset} className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                Clear
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
