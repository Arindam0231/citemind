import { useState, useEffect } from 'react';
import Header from './components/Header';
import UploadRow from './components/UploadRow';
import LeftPanel from './components/LeftPanel';
import ChatPanel from './components/ChatPanel';

function App() {
  const [pptxId, setPptxId] = useState<number | null>(null);
  const [pptxName, setPptxName] = useState<string>('');
  
  const [xlsxId, setXlsxId] = useState<number | null>(null);
  const [xlsxName, setXlsxName] = useState<string>('');

  const [projectId, setProjectId] = useState<number | null>(null);

  useEffect(() => {
    if (pptxId && xlsxId && !projectId) {
      // Both files uploaded, initialize project
      fetch('/api/upload/initialize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pptx_id: pptxId, xlsx_id: xlsxId })
      })
      .then(res => res.json())
      .then(data => {
        setProjectId(data.project_id);
      })
      .catch(err => console.error("Error initializing project:", err));
    }
  }, [pptxId, xlsxId, projectId]);

  const handleUploadPptx = (fileId: number, filename: string) => {
    setPptxId(fileId);
    setPptxName(filename);
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
          <LeftPanel />
          <ChatPanel />
        </div>
      )}
    </div>
  );
}

export default App;
