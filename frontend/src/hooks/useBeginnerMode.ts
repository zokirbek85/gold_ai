"use client";

import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "goldai_beginner_mode";

export function useBeginnerMode(): [boolean, () => void] {
  const [isBeginnerMode, setIsBeginnerMode] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored !== null) {
        setIsBeginnerMode(stored === "true");
      }
    } catch {
      // localStorage not available (SSR)
    }
  }, []);

  const toggleBeginnerMode = useCallback(() => {
    setIsBeginnerMode((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  return [isBeginnerMode, toggleBeginnerMode];
}
