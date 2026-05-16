interface HeaderProps {
  pptxLoaded: boolean;
  xlsxLoaded: boolean;
  pptxName?: string;
  xlsxName?: string;
}

export default function Header({ pptxLoaded, xlsxLoaded, pptxName, xlsxName }: HeaderProps) {
  return (
    <header className="app-header">
      <div className="logo-group">
        <div className="logo-icon">C</div>
        <span className="logo-text">CiteMind</span>
      </div>
      <div className="header-right">
        <div id="pptx-status" className={`file-badge ${pptxLoaded ? 'loaded' : ''}`}>
          <span className="dot"></span> {pptxLoaded && pptxName ? `✓ ${pptxName}` : 'PPTX'}
        </div>
        <div id="xlsx-status" className={`file-badge ${xlsxLoaded ? 'loaded' : ''}`}>
          <span className="dot"></span> {xlsxLoaded && xlsxName ? `✓ ${xlsxName}` : 'XLSX'}
        </div>
        <div className="model-badge">Hello World</div>
      </div>
    </header>
  );
}
