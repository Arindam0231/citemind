import { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import UploadRow from './components/UploadRow';
import LeftPanel from './components/LeftPanel';
import ChatPanel from './components/ChatPanel';

function App() {
  const [pptxId, setPptxId] = useState<number | null>(null);
  const [pptxName, setPptxName] = useState<string>('');
  const [slides, setSlides] = useState<any[]>([]);

  const [xlsxId, setXlsxId] = useState<number | null>(null);
  const [xlsxName, setXlsxName] = useState<string>('');

  const [projectId, setProjectId] = useState<number | null>(null);

  const initializingRef = useRef(false);

  useEffect(() => {
    if (pptxId !== null && xlsxId !== null && !projectId && !initializingRef.current) {
      initializingRef.current = true;  // lock before async call

      fetch('/api/projects/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pptx_file_id: pptxId, xlsx_file_id: xlsxId })
      })
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then(data => setProjectId(data.project_id))
        .catch(err => {
          console.error("Error initializing project:", err);
          initializingRef.current = false;  // reset on failure so user can retry
        });
    }
  }, [pptxId, xlsxId, projectId]);

  const handleUploadPptx = (fileId: number, filename: string, uploadedSlides?: any[]) => {
    setPptxId(fileId);
    setPptxName(filename);
    if (uploadedSlides) {
      setSlides(uploadedSlides);
    }
  };

  const handleUploadXlsx = (fileId: number, filename: string) => {
    setXlsxId(fileId);
    setXlsxName(filename);
  };

  return (
    <div className="app-root" data-theme="dark">
      <Header
        pptxLoaded={!!pptxId}
        xlsxLoaded={!!xlsxId}
        pptxName={pptxName}
        xlsxName={xlsxName}
      />

      {/* If project is initialized, show main workspace, else show upload landing */}
      {!projectId ? (
        <UploadRow
          onUploadPptx={handleUploadPptx}
          onUploadXlsx={handleUploadXlsx}
        />
      ) : (
        <div className="main-layout" style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          <LeftPanel slides={slides} setSlides={setSlides} />
          <ChatPanel />
        </div>
      )}
    </div>
  );
}

export default App;
