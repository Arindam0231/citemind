import React, { useState } from 'react';
import SlideEditor from './SlideEditor';
import type { SlideObject } from './SlideEditor';

interface LeftPanelProps {
  slides: SlideObject[];
  setSlides: React.Dispatch<React.SetStateAction<SlideObject[]>>;
}

export default function LeftPanel({ slides, setSlides }: LeftPanelProps) {
  const [activeTab, setActiveTab] = useState<'slides' | 'data'>('slides');
  const [activeSlideIndex, setActiveSlideIndex] = useState(0);

  const handleSaveSuccess = (updatedSlide: SlideObject) => {
    setSlides((prev) =>
      prev.map((s) => (s.slide_id === updatedSlide.slide_id ? updatedSlide : s))
    );
  };

  const handlePrevSlide = () => {
    setActiveSlideIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNextSlide = () => {
    setActiveSlideIndex((prev) => Math.min(slides.length - 1, prev + 1));
  };

  const hasSlides = slides && slides.length > 0;

  return (
    <div className="left-panel slide-panel" style={{ display: 'flex', flexDirection: 'column', flex: 1, borderRight: '1px solid var(--border)', background: '#0B0F19', overflow: 'hidden' }}>
      {/* Tab bar */}
      <div 
        className="tab-container slide-nav" 
        style={{ 
          display: 'flex', 
          borderBottom: '1px solid var(--border)',
          background: 'rgba(15, 23, 42, 0.6)',
        }}
      >
        <button 
          id="tab-slides-btn" 
          onClick={() => setActiveTab('slides')}
          className={`doc-tab slide-nav-btn ${activeTab === 'slides' ? 'active' : ''}`}
          style={{
            flex: 1,
            padding: '0.75rem 1rem',
            background: activeTab === 'slides' ? 'rgba(29, 158, 117, 0.1)' : 'transparent',
            border: 'none',
            borderBottom: `2px solid ${activeTab === 'slides' ? '#1D9E75' : 'transparent'}`,
            color: activeTab === 'slides' ? '#1D9E75' : '#94A6B8',
            fontSize: '0.9rem',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
        >
          Slides
        </button>
        <button 
          id="tab-data-btn" 
          onClick={() => setActiveTab('data')}
          className={`doc-tab slide-nav-btn ${activeTab === 'data' ? 'active' : ''}`}
          style={{
            flex: 1,
            padding: '0.75rem 1rem',
            background: activeTab === 'data' ? 'rgba(29, 158, 117, 0.1)' : 'transparent',
            border: 'none',
            borderBottom: `2px solid ${activeTab === 'data' ? '#1D9E75' : 'transparent'}`,
            color: activeTab === 'data' ? '#1D9E75' : '#94A6B8',
            fontSize: '0.9rem',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
        >
          Data Sheets
        </button>
      </div>
      
      {/* Tab content */}
      <div id="tab-content" className="tab-content slide-viewer" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {!hasSlides ? (
          <div className="empty-state" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, padding: '2rem' }}>
            <div className="empty-state-icon" style={{ fontSize: '3rem', marginBottom: '1rem' }}>📊</div>
            <div className="empty-state-text" style={{ color: '#94A6B8', fontSize: '1rem', fontWeight: 500 }}>
              Upload a .pptx presentation to view and edit slides
            </div>
          </div>
        ) : activeTab === 'slides' ? (
          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
            {/* Editor Canvas Container */}
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <SlideEditor 
                slide={slides[activeSlideIndex]} 
                onSaveSuccess={handleSaveSuccess} 
              />
            </div>

            {/* Slide Navigation controls */}
            <div 
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '0.75rem 1.5rem',
                borderTop: '1px solid var(--border)',
                background: 'rgba(15, 23, 42, 0.8)',
              }}
            >
              <button 
                onClick={handlePrevSlide}
                disabled={activeSlideIndex === 0}
                style={{
                  padding: '0.4rem 0.8rem',
                  fontSize: '0.85rem',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: activeSlideIndex === 0 ? '#475569' : '#F1F5F9',
                  cursor: activeSlideIndex === 0 ? 'not-allowed' : 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                ◀ Previous Slide
              </button>

              <span style={{ fontSize: '0.85rem', color: '#94A6B8', fontWeight: 500 }}>
                Slide {activeSlideIndex + 1} of {slides.length}
              </span>

              <button 
                onClick={handleNextSlide}
                disabled={activeSlideIndex === slides.length - 1}
                style={{
                  padding: '0.4rem 0.8rem',
                  fontSize: '0.85rem',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: activeSlideIndex === slides.length - 1 ? '#475569' : '#F1F5F9',
                  cursor: activeSlideIndex === slides.length - 1 ? 'not-allowed' : 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                Next Slide ▶
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, padding: '2rem', textAlign: 'center' }}>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📈</div>
            <h3 style={{ color: '#F1F5F9', marginBottom: '0.5rem' }}>Financial Data Sources Loaded</h3>
            <p style={{ color: '#94A6B8', maxWidth: '360px', fontSize: '0.9rem', lineHeight: '1.5' }}>
              Your financial sheets are parsed. You can double-click and edit slide values here, then ask the AI agent in the Chat panel to perform mappings and check database integrity.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
