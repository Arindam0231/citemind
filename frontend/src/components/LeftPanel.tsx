

export default function LeftPanel() {
  return (
    <div className="left-panel slide-panel" style={{ display: 'flex', flexDirection: 'column', flex: 1, borderRight: '1px solid var(--border)' }}>
      {/* Tab bar */}
      <div className="tab-container slide-nav">
        <button id="tab-slides-btn" className="doc-tab slide-nav-btn active">
          Slides
        </button>
        <button id="tab-data-btn" className="doc-tab slide-nav-btn">
          Data
        </button>
      </div>
      
      {/* Tab content */}
      <div id="tab-content" className="tab-content slide-viewer" style={{ flex: 1 }}>
        <div className="empty-state">
          <div className="empty-state-icon">📊</div>
          <div className="empty-state-text">
            Upload a .pptx to view slides
          </div>
        </div>
      </div>
      
      {/* Slide preview (hidden by default) */}
      <div id="slide-preview" className="slide-preview" style={{ display: "none" }}></div>
    </div>
  );
}
