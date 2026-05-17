import { useState, useEffect } from 'react';

export interface Shape {
  id: number;
  slide_id: number;
  left_emu: number;
  top_emu: number;
  width_emu: number;
  height_emu: number;
  text: string;
  font_size: number;   // in EMU
  shape_type: string;
  is_claim: boolean;
  status: 'matched' | 'unmatched' | null;
}

interface UseShapesResult {
  shapes: Shape[];
  loading: boolean;
  error: string | null;
}

/**
 * Fetches shapes for a given slide from the backend.
 *
 * @param slideId - The slide whose shapes should be loaded.
 * @returns `{ shapes, loading, error }`
 */
export function useShapes(slideId: number): UseShapesResult {
  const [shapes, setShapes]   = useState<Shape[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    fetch(`/api/slides/${slideId}/shapes`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch shapes`);
        return res.json() as Promise<Shape[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setShapes(data);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [slideId]);

  return { shapes, loading, error };
}
