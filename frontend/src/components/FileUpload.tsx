import { useCallback, useState, useRef } from 'react';

interface FileUploadProps {
  onUpload: (files: File[]) => void;
  multiple?: boolean;
  loading?: boolean;
  accept?: string;
  label?: string;
}

export default function FileUpload({
  onUpload,
  multiple = false,
  loading = false,
  accept = '.pdf',
  label = 'Upload PDF',
}: FileUploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const files = Array.from(e.dataTransfer.files).filter((f) =>
        f.name.toLowerCase().endsWith('.pdf')
      );
      if (files.length > 0) onUpload(multiple ? files : [files[0]]);
    },
    [onUpload, multiple]
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) onUpload(multiple ? files : [files[0]]);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      onClick={() => !loading && inputRef.current?.click()}
      className={`
        border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all
        ${dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'}
        ${loading ? 'opacity-60 cursor-wait' : ''}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={handleChange}
        className="hidden"
      />
      {loading ? (
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Processing...</p>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <span className="text-3xl">📎</span>
          <p className="text-sm font-medium text-gray-700">{label}</p>
          <p className="text-xs text-gray-400">
            Drag & drop or click to browse {multiple ? '(multiple files)' : ''}
          </p>
        </div>
      )}
    </div>
  );
}
