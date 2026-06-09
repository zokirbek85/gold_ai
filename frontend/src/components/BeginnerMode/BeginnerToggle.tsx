"use client";

interface BeginnerToggleProps {
  isBeginnerMode: boolean;
  onToggle: () => void;
}

export function BeginnerToggle({ isBeginnerMode, onToggle }: BeginnerToggleProps) {
  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-colors text-sm"
      style={{
        borderColor: isBeginnerMode ? "var(--gold)" : "var(--surface-2)",
        background:  isBeginnerMode ? "rgba(212,175,55,0.1)" : "var(--surface-1)",
        color:       isBeginnerMode ? "var(--gold)" : "var(--text-muted)",
      }}
    >
      <span className="text-base">📚</span>
      <span className="font-medium">Boshlovchi rejimi</span>
      <div
        className={`w-8 h-4 rounded-full flex items-center transition-colors ${
          isBeginnerMode ? "bg-[var(--gold)]" : "bg-[#2a2a3a]"
        }`}
      >
        <div
          className={`w-3 h-3 rounded-full bg-white shadow transition-transform mx-0.5 ${
            isBeginnerMode ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </div>
    </button>
  );
}
