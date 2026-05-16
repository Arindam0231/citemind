import { useState, useRef } from 'react';

interface UploadRowProps {
  onUploadPptx: (fileId: number, filename: string) => void;
  onUploadXlsx: (fileId: number, filename: string) => void;
}

export default function UploadRow({ onUploadPptx, onUploadXlsx }: UploadRowProps) {
  const [pptxLoading, setPptxLoading] = useState(false);
  const [xlsxLoading, setXlsxLoading] = useState(false);

  const pptxInputRef = useRef<HTMLInputElement>(null);
  const xlsxInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File, type: 'pptx' | 'xlsx') => {
    if (type === 'pptx') setPptxLoading(true);
    else setXlsxLoading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`/api/upload/${type}`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("Upload failed");
      
      const data = await response.json();
      if (type === 'pptx') onUploadPptx(data.file_id, data.filename);
      else onUploadXlsx(data.file_id, data.filename);

    } catch (err) {
      console.error(err);
      alert(`Error uploading ${type.toUpperCase()} file`);
    } finally {
      if (type === 'pptx') setPptxLoading(false);
      else setXlsxLoading(false);
    }
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>, type: 'pptx' | 'xlsx') => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleUpload(e.dataTransfer.files[0], type);
    }
  };

  return (
    <div className="upload-landing">
      <div className="upload-title">CiteMind</div>
      <div className="upload-subtitle">
        Upload your presentation and data source to automatically verify claims and format citations.
      </div>
      <div className="upload-row" id="upload-row">
        
        {/* PPTX Drop Zone */}
        <div className="upload-component">
          <div 
            className="drop-zone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onDrop(e, 'pptx')}
            onClick={() => pptxInputRef.current?.click()}
          >
            {pptxLoading ? (
              <>
                <div className="orbital"></div>
                <div className="drop-zone-label">Parsing PPTX...</div>
              </>
            ) : (
              <>
                <div className="drop-zone-icon">📊</div>
                <div className="drop-zone-label">Drop .pptx file here</div>
                <div className="drop-zone-hint">or click to browse</div>
              </>
            )}
          </div>
          <input 
            type="file" 
            accept=".pptx" 
            ref={pptxInputRef} 
            style={{ display: 'none' }} 
            onChange={(e) => e.target.files && handleUpload(e.target.files[0], 'pptx')}
          />
        </div>

        {/* XLSX Drop Zone */}
        <div className="upload-component">
          <div 
            className="drop-zone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onDrop(e, 'xlsx')}
            onClick={() => xlsxInputRef.current?.click()}
          >
            {xlsxLoading ? (
              <>
                <div className="orbital"></div>
                <div className="drop-zone-label">Parsing XLSX...</div>
              </>
            ) : (
              <>
                <div className="drop-zone-icon">📈</div>
                <div className="drop-zone-label">Drop .xlsx file here</div>
                <div className="drop-zone-hint">or click to browse</div>
              </>
            )}
          </div>
          <input 
            type="file" 
            accept=".xlsx" 
            ref={xlsxInputRef} 
            style={{ display: 'none' }} 
            onChange={(e) => e.target.files && handleUpload(e.target.files[0], 'xlsx')}
          />
        </div>

      </div>
    </div>
  );
}
