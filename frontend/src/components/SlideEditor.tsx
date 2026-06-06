import { useState, useEffect } from 'react';

export interface ShapeRun {
  text: string;
  bold: boolean;
  italic: boolean;
  font_size: number;
  color: string;
  alignment: 'LEFT' | 'CENTER' | 'RIGHT' | 'JUSTIFY';
}

export interface SlideShape {
  id: string;
  pptx_shape_id: number;
  shape_name: string;
  shape_type: string;
  x_pct: number;
  y_pct: number;
  w_pct: number;
  h_pct: number;
  full_text: string;
  runs_json: ShapeRun[];
  z_order: number;
}

export interface SlideObject {
  slide_id: string;
  slide_index: number;
  png_url: string;
  shapes: SlideShape[];
}

interface SlideEditorProps {
  slide: SlideObject;
  onSaveSuccess?: (updatedSlide: SlideObject) => void;
}

export default function SlideEditor({ slide, onSaveSuccess }: SlideEditorProps) {
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedTexts, setEditedTexts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');

  // Reset local edits when the slide changes
  useEffect(() => {
    setEditedTexts({});
    setIsEditMode(false);
    setSuccessMsg('');
  }, [slide.slide_id]);

  const handleTextChange = (shapeId: string, text: string) => {
    setEditedTexts((prev) => ({
      ...prev,
      [shapeId]: text,
    }));
  };

  const isDirty = Object.keys(editedTexts).length > 0;

  const handleSave = async () => {
    if (!isDirty) return;
    setSaving(true);
    setSuccessMsg('');

    const payload = Object.entries(editedTexts).map(([id, full_text]) => ({
      id,
      full_text,
    }));

    try {
      const response = await fetch(`/api/slides/${slide.slide_id}/shapes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error('Save failed');

      const data = await response.json();
      setSuccessMsg('Slide successfully updated!');
      setEditedTexts({});
      setIsEditMode(false);

      if (onSaveSuccess) {
        onSaveSuccess(data);
      }

      // Hide success message after 3 seconds
      setTimeout(() => setSuccessMsg(''), 3000);
    } catch (err) {
      console.error(err);
      alert('Failed to save changes to slide.');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditedTexts({});
    setIsEditMode(false);
  };

  return (
    <div className="slide-editor-container" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Control bar */}
      <div 
        className="slide-editor-controls"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.75rem 1rem',
          borderBottom: '1px solid var(--border)',
          background: 'rgba(30, 41, 59, 0.4)',
          backdropFilter: 'blur(8px)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span 
            className="editor-mode-badge"
            style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              padding: '0.25rem 0.5rem',
              borderRadius: '4px',
              background: isEditMode ? 'rgba(29, 158, 117, 0.2)' : 'rgba(148, 163, 184, 0.1)',
              color: isEditMode ? '#1D9E75' : '#94A6B8',
              border: `1px solid ${isEditMode ? 'rgba(29, 158, 117, 0.4)' : 'rgba(148, 163, 184, 0.2)'}`,
              transition: 'all 0.2s ease',
            }}
          >
            {isEditMode ? 'Editing Mode' : 'Viewing Mode'}
          </span>
          <span style={{ fontSize: '0.8rem', color: '#64748B' }}>
            {isEditMode ? 'Type in boxes to edit. Click Save to write to PPTX.' : 'Double-click anywhere on slide to edit.'}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          {successMsg && (
            <span style={{ color: '#1D9E75', fontSize: '0.85rem', fontWeight: 500, marginRight: '0.5rem' }}>
              ✓ {successMsg}
            </span>
          )}

          {isEditMode ? (
            <>
              <button 
                onClick={handleCancel}
                className="btn btn-secondary"
                style={{
                  padding: '0.375rem 0.75rem',
                  fontSize: '0.85rem',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#94A6B8',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button 
                onClick={handleSave}
                disabled={!isDirty || saving}
                className="btn btn-primary"
                style={{
                  padding: '0.375rem 0.75rem',
                  fontSize: '0.85rem',
                  borderRadius: '6px',
                  background: isDirty ? '#1D9E75' : 'rgba(29, 158, 117, 0.3)',
                  border: 'none',
                  color: '#FFFFFF',
                  cursor: isDirty && !saving ? 'pointer' : 'not-allowed',
                  opacity: saving ? 0.7 : 1,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                }}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </>
          ) : (
            <button 
              onClick={() => setIsEditMode(true)}
              className="btn btn-primary"
              style={{
                padding: '0.375rem 0.75rem',
                fontSize: '0.85rem',
                borderRadius: '6px',
                background: '#1D9E75',
                border: 'none',
                color: '#FFFFFF',
                cursor: 'pointer',
              }}
            >
              Edit Slide
            </button>
          )}
        </div>
      </div>

      {/* Editor Canvas Area */}
      <div 
        style={{
          flex: 1,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          background: '#0F172A',
          padding: '1.5rem',
          overflow: 'auto',
        }}
      >
        <div 
          id="slide-editor-canvas"
          onDoubleClick={() => {
            if (!isEditMode) setIsEditMode(true);
          }}
          style={{
            position: 'relative',
            width: '100%',
            maxWidth: '960px',
            aspectRatio: '16/9',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4)',
            borderRadius: '8px',
            overflow: 'hidden',
            background: '#000000',
            userSelect: 'none',
          }}
        >
          {/* Base Layer PNG */}
          <img 
            src={slide.png_url} 
            alt={`Slide ${slide.slide_index + 1}`}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              pointerEvents: 'none',
            }}
          />

          {/* Overlay Textarea Shapes Layer */}
          <div 
            style={{
              position: 'absolute',
              inset: 0,
              pointerEvents: isEditMode ? 'auto' : 'none',
            }}
          >
            {slide.shapes.map((shape) => {
              const firstRun = shape.runs_json && shape.runs_json[0];
              const value = editedTexts[shape.id] !== undefined ? editedTexts[shape.id] : shape.full_text;

              // Don't render overlay textareas for shapes that have no text and are not being edited
              // unless we are in edit mode and they have a valid shape type that might contain text.
              if (!shape.full_text && editedTexts[shape.id] === undefined && !isEditMode) {
                return null;
              }

              // Font Styling
              const fontSize = firstRun?.font_size ? `${firstRun.font_size}pt` : '14pt';
              const fontWeight = firstRun?.bold ? 'bold' : 'normal';
              const fontStyle = firstRun?.italic ? 'italic' : 'normal';
              const color = firstRun?.color || '#000000';
              let textAlign: 'left' | 'center' | 'right' | 'justify' = 'left';
              if (firstRun?.alignment) {
                const alignVal = firstRun.alignment.toLowerCase();
                if (alignVal === 'center' || alignVal === 'right' || alignVal === 'justify') {
                  textAlign = alignVal;
                }
              }

              return (
                <textarea
                  key={shape.id}
                  value={value}
                  onChange={(e) => handleTextChange(shape.id, e.target.value)}
                  placeholder={isEditMode ? 'Empty Shape' : ''}
                  style={{
                    position: 'absolute',
                    left: `${shape.x_pct * 100}%`,
                    top: `${shape.y_pct * 100}%`,
                    width: `${shape.w_pct * 100}%`,
                    height: `${shape.h_pct * 100}%`,
                    zIndex: shape.z_order,
                    fontSize: `calc(${fontSize} * 0.08vw + 4px)`, // Scaled responsively with container width!
                    fontWeight,
                    fontStyle,
                    color,
                    textAlign,
                    pointerEvents: isEditMode ? 'auto' : 'none',
                    background: 'transparent',
                    border: '1px dashed transparent',
                    outline: 'none',
                    resize: 'none',
                    overflow: 'hidden',
                    fontFamily: 'Calibri, Arial, sans-serif',
                    lineHeight: 1.25,
                    padding: '2px',
                    margin: 0,
                    boxSizing: 'border-box',
                    transition: 'border-color 0.15s ease, background-color 0.15s ease',
                  }}
                  className="shape-overlay-textarea"
                />
              );
            })}
          </div>
        </div>
      </div>

      {/* Embedded inline CSS for micro-animations and dashed borders */}
      <style>{`
        .shape-overlay-textarea:hover {
          border-color: rgba(29, 158, 117, 0.4) !important;
          background: rgba(29, 158, 117, 0.02);
        }
        .shape-overlay-textarea:focus {
          border-color: #1D9E75 !important;
          background: rgba(255, 255, 255, 0.05);
          box-shadow: 0 0 0 2px rgba(29, 158, 117, 0.15);
        }
      `}</style>
    </div>
  );
}
