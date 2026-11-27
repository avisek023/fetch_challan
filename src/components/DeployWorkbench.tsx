import React, { useMemo, useState } from 'react';
import { Check, Copy, Terminal } from 'lucide-react';

type CloudTarget = 'railway' | 'render' | 'koyeb' | 'docker';

const PLATFORM_STEPS: Record<
  CloudTarget,
  {
    name: string;
    subtitle: string;
    steps: { title: string; detail: string; command?: string }[];
  }
> = {
  railway: {
    name: 'Railway (Recommended)',
    subtitle: 'Zero-config Dockerfile detection with persistent port 8080 health checks',
    steps: [
      {
        title: '01. Push from AI Studio to GitHub',
        detail:
          'Use Save to GitHub in AI Studio (or unzip the downloaded bundle into a private GitHub repository). Confirm bot.py, browser_manager.py, selectors.py, Dockerfile, and requirements.txt sit at the repository root.',
      },
      {
        title: '02. Create Railway Service from GitHub',
        detail:
          'Open Railway -> New Project -> Deploy from GitHub repo -> select your repository. Railway automatically builds from the root Dockerfile using mcr.microsoft.com/playwright/python:v1.58.0-noble.',
      },
      {
        title: '03. Configure Variables & Healthcheck',
        detail:
          'Add TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, HEADLESS_MODE=true, optional PROXY_URL, and PORT=8080 under Variables. Set Healthcheck Path to /health in Service Settings.',
      },
      {
        title: '04. Verify Live Container',
        detail: 'Check Railway deploy logs for the aiohttp server startup message and test /start in Telegram.',
        command: 'curl -s https://<your-railway-domain>/health',
      },
    ],
  },
  render: {
    name: 'Render',
    subtitle: 'Managed Docker Web Service with automated GitHub redeploys',
    steps: [
      {
        title: '01. Connect GitHub Repository',
        detail: 'In Render Dashboard, click New -> Web Service and select your pushed GitHub repo.',
      },
      {
        title: '02. Select Docker Runtime',
        detail: 'Choose Environment: Docker so Render builds directly from the repository Dockerfile.',
      },
      {
        title: '03. Set Health Check Path & Env Vars',
        detail:
          'Set Health Check Path to /health and add TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, HEADLESS_MODE=true, PROXY_URL, and PORT=8080.',
      },
    ],
  },
  koyeb: {
    name: 'Koyeb',
    subtitle: 'Global edge Docker runtime with HTTP liveness probing',
    steps: [
      {
        title: '01. Create Web Service from GitHub',
        detail: 'In Koyeb, create a new App -> GitHub -> pick your repository and set Builder to Dockerfile.',
      },
      {
        title: '02. Expose Port 8080 Health Probe',
        detail: 'Configure HTTP port 8080 with Health Check Path /health so Koyeb keeps the long-polling worker active.',
      },
      {
        title: '03. Inject Secrets',
        detail: 'Add TELEGRAM_BOT_TOKEN and ALLOWED_USER_IDS as encrypted environment secrets alongside HEADLESS_MODE=true and PORT=8080.',
      },
    ],
  },
  docker: {
    name: 'Local Docker',
    subtitle: 'Build and verify the exact production container locally before pushing',
    steps: [
      {
        title: '01. Create local .env file',
        detail: 'Copy .env.example to .env and fill in your @BotFather token and numeric user ID from @userinfobot.',
        command: 'cp .env.example .env',
      },
      {
        title: '02. Build container image',
        detail: 'Uses the pre-baked Playwright Ubuntu Noble image so Chromium needs no download at build time.',
        command: 'docker build -t parivahan-echallan-bot .',
      },
      {
        title: '03. Run bot + health check server',
        detail: 'Starts the Telegram polling worker and exposes port 8080 locally.',
        command: 'docker run --rm --env-file .env -p 8080:8080 parivahan-echallan-bot',
      },
      {
        title: '04. Verify /health endpoint',
        detail: 'Confirm HTTP 200 JSON response from the aiohttp health server.',
        command: 'curl -s http://localhost:8080/health',
      },
    ],
  },
};

export const DeployWorkbench: React.FC = () => {
  const [target, setTarget] = useState<CloudTarget>('railway');
  const [allowedIds, setAllowedIds] = useState('123456789');
  const [proxyUrl, setProxyUrl] = useState('');
  const [port, setPort] = useState('8080');
  const [headless, setHeadless] = useState(true);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const generatedEnv = useMemo(() => {
    return [
      'TELEGRAM_BOT_TOKEN=REPLACE_WITH_BOTFATHER_TOKEN',
      `ALLOWED_USER_IDS=${allowedIds.trim() || '123456789'}`,
      `HEADLESS_MODE=${headless ? 'true' : 'false'}`,
      `PROXY_URL=${proxyUrl.trim()}`,
      `PORT=${port.trim() || '8080'}`,
    ].join('\n');
  }, [allowedIds, headless, proxyUrl, port]);

  const handleCopy = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(id);
      window.setTimeout(() => setCopiedKey(null), 1600);
    } catch {
      // Ignore clipboard failures
    }
  };

  const activeGuide = PLATFORM_STEPS[target];

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Cloud Deployment Guide & Environment Builder
          </h1>
          <p className="mt-1.5 text-sm text-slate-600 max-w-2xl">
            Deploy directly from GitHub via the root <span className="font-mono text-slate-800">Dockerfile</span>.
            Chromium and Ubuntu Noble libraries are pre-installed in the base image.
          </p>
        </div>

        <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-md">
          {(
            [
              ['railway', 'Railway'],
              ['render', 'Render'],
              ['koyeb', 'Koyeb'],
              ['docker', 'Local Docker'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTarget(key)}
              className={`px-3 py-1.5 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                target === key ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Deployment Steps */}
        <div className="lg:col-span-7 space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{activeGuide.name}</h2>
            <p className="text-sm text-slate-600 mt-0.5">{activeGuide.subtitle}</p>
          </div>

          <div className="space-y-4">
            {activeGuide.steps.map((step) => (
              <div key={step.title} className="p-5 border border-slate-200 rounded-lg bg-white">
                <h3 className="text-sm font-semibold text-slate-900">{step.title}</h3>
                <p className="mt-1.5 text-sm text-slate-600 leading-relaxed">{step.detail}</p>
                {step.command && (
                  <div className="mt-3 flex items-center justify-between gap-3 px-3.5 py-2.5 bg-slate-950 text-slate-100 rounded-md font-mono text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <Terminal className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <code className="truncate">{step.command}</code>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleCopy(step.title, step.command!)}
                      className="inline-flex items-center gap-1 text-slate-300 hover:text-white shrink-0 cursor-pointer"
                    >
                      {copiedKey === step.title ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                      <span>{copiedKey === step.title ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* .env Config Template Builder */}
        <div className="lg:col-span-5 border border-slate-200 rounded-lg bg-white overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-200 bg-slate-50">
            <h3 className="text-sm font-semibold text-slate-900">Environment Variable Template</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Customize non-secret values below and paste into your cloud host Variables tab. Add your{' '}
              <span className="font-mono">@BotFather</span> token directly in Railway/Render/Koyeb.
            </p>
          </div>

          <div className="p-5 space-y-4">
            <div>
              <label htmlFor="allowed-ids" className="block text-xs font-medium text-slate-700 mb-1.5">
                ALLOWED_USER_IDS (comma-separated numeric Telegram IDs)
              </label>
              <input
                id="allowed-ids"
                type="text"
                value={allowedIds}
                onChange={(e) => setAllowedIds(e.target.value)}
                placeholder="123456789,987654321"
                className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600"
              />
            </div>

            <div>
              <label htmlFor="proxy-url" className="block text-xs font-medium text-slate-700 mb-1.5">
                PROXY_URL (optional — recommended if deploying outside India)
              </label>
              <input
                id="proxy-url"
                type="text"
                value={proxyUrl}
                onChange={(e) => setProxyUrl(e.target.value)}
                placeholder="http://user:pass@in-proxy.example.com:8080"
                className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="health-port" className="block text-xs font-medium text-slate-700 mb-1.5">
                  PORT
                </label>
                <input
                  id="health-port"
                  type="text"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono text-slate-900 bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600"
                />
              </div>
              <div>
                <span className="block text-xs font-medium text-slate-700 mb-1.5">HEADLESS_MODE</span>
                <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-md">
                  <button
                    type="button"
                    onClick={() => setHeadless(true)}
                    className={`flex-1 py-1 text-xs font-mono rounded transition-colors cursor-pointer ${
                      headless ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
                    }`}
                  >
                    true
                  </button>
                  <button
                    type="button"
                    onClick={() => setHeadless(false)}
                    className={`flex-1 py-1 text-xs font-mono rounded transition-colors cursor-pointer ${
                      !headless ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
                    }`}
                  >
                    false
                  </button>
                </div>
              </div>
            </div>

            <div className="pt-2">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-medium text-slate-700">Generated .env preview</span>
                <button
                  type="button"
                  onClick={() => handleCopy('env-block', generatedEnv)}
                  className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800 cursor-pointer"
                >
                  {copiedKey === 'env-block' ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                  <span>{copiedKey === 'env-block' ? 'Copied' : 'Copy .env'}</span>
                </button>
              </div>
              <pre className="p-3.5 rounded-md bg-slate-950 text-emerald-300 font-mono text-xs overflow-x-auto leading-6">
                {generatedEnv}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
