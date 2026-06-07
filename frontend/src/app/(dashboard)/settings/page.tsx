"use client";

import { useState } from "react";
import { Card, CardHeader, PageHeader } from "@/components/ui";
import { Settings, Server, Key } from "lucide-react";

const ENV_VARS = [
  { key: "ANTHROPIC_API_KEY", desc: "Claude AI analysis (primary)" },
  { key: "OPENAI_API_KEY", desc: "OpenAI GPT-4o fallback" },
  { key: "TELEGRAM_BOT_TOKEN", desc: "Telegram alert bot" },
  { key: "TELEGRAM_CHAT_ID", desc: "Telegram target chat ID" },
  { key: "MT4_HOST", desc: "MT4 Windows machine IP" },
  { key: "MT4_CMD_PORT", desc: "ZeroMQ command port (default 32768)" },
  { key: "MT4_DATA_PORT", desc: "ZeroMQ data port (default 32769)" },
  { key: "CORS_ORIGINS", desc: "Comma-separated allowed origins" },
];

export default function SettingsPage() {
  const [saved, setSaved] = useState(false);

  function save() {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5">
      <PageHeader title="Settings" subtitle="Dashboard configuration and backend environment variables" />

      {/* Backend config reference */}
      <Card>
        <div className="p-5">
          <CardHeader icon={<Server className="w-4 h-4" />} title="Backend Environment Variables" />
          <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
            Configure these in your <code className="text-[var(--gold)]">.env</code> file and restart the backend container.
          </p>
          <div className="space-y-2">
            {ENV_VARS.map(({ key, desc }) => (
              <div
                key={key}
                className="flex items-start gap-4 px-3 py-2.5 rounded-lg"
                style={{ background: "var(--surface-2)" }}
              >
                <code className="text-xs font-mono shrink-0 mt-0.5" style={{ color: "var(--gold)" }}>
                  {key}
                </code>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Quick links */}
      <Card>
        <div className="p-5">
          <CardHeader icon={<Key className="w-4 h-4" />} title="Quick Links" />
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "API Docs (Swagger)", href: "/api/docs" },
              { label: "API ReDoc", href: "/api/redoc" },
              { label: "Health Check", href: "/api/v1/health" },
              { label: "MT4 Guide", href: "/MT4_CONNECTION_GUIDE.md" },
            ].map(l => (
              <a
                key={l.label}
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-ghost text-xs py-2 justify-center"
              >
                {l.label} ↗
              </a>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
