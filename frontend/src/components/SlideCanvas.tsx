import React from 'react';
import { useShapes, type Shape } from '../hooks/useShapes';
import {
  emuToPercent,
  emuFontSizeToPx,
  SLIDE_WIDTH_EMU,
  SLIDE_HEIGHT_EMU,
} from '../utils/emu';

// ---------------------------------------------------------------------------
// ShapeBox
// ---------------------------------------------------------------------------

interface ShapeBoxProps {
  shape: Shape;
  onClaimClick: (shapeId: number) => void;
}

/**
 * Renders a single PPTX shape as an absolutely-positioned div inside the slide
 * canvas. Position and size are percentage-based (derived from EMU → percent
 * conversion), so the component scales correctly at any container width.
 */
const ShapeBox: React.FC<ShapeBoxProps> = ({ shape, onClaimClick }) => {
  const {
    id,
    left_emu,
    top_emu,
    width_emu,
    height_emu,
    text,
    font_size,
    is_claim,
    status,
  } = shape;

  // --- Border highlight for claim shapes ---
  let border = 'none';
  if (is_claim) {
    if (status === 'matched')   border = '2px solid #1D9E75';
    else if (status === 'unmatched') border = '2px solid #D85A30';
    // null → no border (leave as 'none')
  }

  const handleClick = () => {
    if (is_claim) onClaimClick(id);
  };

  const style: React.CSSProperties = {
    position:  'absolute',
    left:      emuToPercent(left_emu,   SLIDE_WIDTH_EMU),
    top:       emuToPercent(top_emu,    SLIDE_HEIGHT_EMU),
    width:     emuToPercent(width_emu,  SLIDE_WIDTH_EMU),
    height:    emuToPercent(height_emu, SLIDE_HEIGHT_EMU),
    fontSize:  `${emuFontSizeToPx(font_size)}px`,
    border,
    cursor:    is_claim ? 'pointer' : 'default',
    overflow:  'hidden',
    boxSizing: 'border-box',
    // Subtle transition for interactive claim shapes
    transition: is_claim ? 'box-shadow 0.15s ease, border-color 0.15s ease' : undefined,
  };

  return (
    <div
      id={`shape-${id}`}
      style={style}
      onClick={handleClick}
      role={is_claim ? 'button' : undefined}
      aria-label={is_claim ? `Claim: ${text}` : undefined}
      tabIndex={is_claim ? 0 : undefined}
      onKeyDown={is_claim ? (e) => { if (e.key === 'Enter' || e.key === ' ') handleClick(); } : undefined}
    >
      {text}
    </div>
  );
};

// ---------------------------------------------------------------------------
// SlideCanvas
// ---------------------------------------------------------------------------

export interface SlideCanvasProps {
  slideId: number;
  onClaimClick: (shapeId: number) => void;
}

/**
 * Fetches all shapes for `slideId` and renders them inside a 16:9 slide
 * container. All shapes are percentage-positioned so the canvas scales
 * fluidly to any container width with no layout shift after load.
 */
const SlideCanvas: React.FC<SlideCanvasProps> = ({ slideId, onClaimClick }) => {
  const { shapes, loading, error } = useShapes(slideId);

  // --- Outer wrapper enforces 16:9 at all times via aspect-ratio ---
  const canvasStyle: React.CSSProperties = {
    position:    'relative',
    width:       '100%',
    aspectRatio: '16 / 9',
    background:  '#fff',
    overflow:    'hidden',
    // Prevent any layout shift — the canvas box is always 16:9 regardless of
    // whether shapes have loaded yet.
    boxSizing:   'border-box',
  };

  // --- Centered spinner overlay (shown during fetch) ---
  const overlayStyle: React.CSSProperties = {
    position:       'absolute',
    inset:          0,
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    background:     'rgba(255, 255, 255, 0.75)',
    zIndex:         10,
  };

  if (error) {
    return (
      <div style={canvasStyle} id={`slide-canvas-${slideId}`}>
        <div style={{ ...overlayStyle, flexDirection: 'column', gap: '0.5rem' }}>
          <span style={{ fontSize: '1.5rem' }}>⚠️</span>
          <span style={{ color: '#D85A30', fontWeight: 600, fontSize: '0.875rem' }}>
            {error}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div style={canvasStyle} id={`slide-canvas-${slideId}`}>
      {/* Loading spinner — rendered inside the 16:9 box so no layout shift */}
      {loading && (
        <div style={overlayStyle}>
          <SpinnerIcon />
        </div>
      )}

      {/* Shape layer */}
      {shapes.map((shape) => (
        <ShapeBox key={shape.id} shape={shape} onClaimClick={onClaimClick} />
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// SpinnerIcon — inline SVG, zero dependencies
// ---------------------------------------------------------------------------

const SpinnerIcon: React.FC = () => (
  <svg
    width="36"
    height="36"
    viewBox="0 0 36 36"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    style={{ animation: 'slide-canvas-spin 0.8s linear infinite' }}
    aria-label="Loading"
  >
    <style>{`
      @keyframes slide-canvas-spin {
        from { transform: rotate(0deg); }
        to   { transform: rotate(360deg); }
      }
    `}</style>
    <circle
      cx="18" cy="18" r="15"
      stroke="#e2e8f0"
      strokeWidth="3"
    />
    <path
      d="M18 3 A15 15 0 0 1 33 18"
      stroke="#1D9E75"
      strokeWidth="3"
      strokeLinecap="round"
    />
  </svg>
);

export default SlideCanvas;
