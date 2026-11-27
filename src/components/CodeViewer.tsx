import React, { useMemo, useState } from 'react';
import { Check, Copy, Download, Search } from 'lucide-react';
import type { DeliverableFile } from '../data/projectFiles';

interface CodeViewerProps {
  file: DeliverableFile;
  globalQuery: string;
}

const PYTHON_KEYWORDS = new Set([
  'async',
  'await',
  'def',
  'class',
  'return',
  'if',
  'elif',
  'else',
  'for',
  'in',
  'while',
  'try',
  'except',
  'finally',
  'with',
  'as',
  'import',
  'from',
  'raise',
  'pass',
  'break',
  'continue',
  'and',
  'or',
  'not',
  'is',
  'None',
  'True',
  'False',
  'assert',
  'lambda',
]);

const DOCKER_KEYWORDS = new Set([
  'FROM',
  'ENV',
  'WORKDIR',
  'COPY',
  'RUN',
  'EXPOSE',
  'HEALTHCHECK',
  'CMD',
  'ENTRYPOINT',
]);

function renderHighlightedLine(line: string, language: DeliverableFile['language']): React.ReactNode {
  const trimmed = line.trimStart();

  if (language === 'python' || language === 'dockerfile' || language === 'env') {
    if (trimmed.startsWith('#')) {
      return <span className="text-slate-400">{line}</span>;
    }
  }

  if (language === 'dockerfile') {
    const firstSpace = line.indexOf(' ');
    const instruction = firstSpace === -1 ? line : line.slice(0, firstSpace);
    if (DOCKER_KEYWORDS.has(instruction)) {
      return (
        <>
          <span className="text-sky-400 font-medium">{instruction}</span>
          <span className="text-slate-200">{firstSpace === -1 ? '' : line.slice(firstSpace)}</span>
        </>
      );
    }
  }

  if (language === 'env') {
    const eqIndex = line.indexOf('=');
    if (eqIndex > 0) {
      return (
        <>
          <span className="text-sky-300">{line.slice(0, eqIndex)}</span>
          <span className="text-slate-400">=</span>
          <span className="text-emerald-300">{line.slice(eqIndex + 1)}</span>
        </>
      );
    }
  }

  if (language === 'markdown') {
    if (trimmed.startsWith('#')) {
      return <span className="text-sky-300 font-medium">{line}</span>;
    }
    if (trimmed.startsWith('|')) {
      return <span className="text-slate-300">{line}</span>;
    }
    if (trimmed.startsWith('```')) {
      return <span className="text-amber-300">{line}</span>;
    }
  }

  if (language === 'python') {
    if (trimmed.startsWith('@')) {
      return <span className="text-amber-300">{line}</span>;
    }
    if (trimmed.startsWith('"""') || trimmed.startsWith("'''")) {
      return <span className="text-emerald-300/90">{line}</span>;
    }

    // Tokenize Python line cleanly without regex-HTML injection
    const tokens = line.split(/(\s+|"[^"]*"|'[^']*'|[()[\]{}:.,=])/g).filter(Boolean);
    return tokens.map((tok, idx) => {
      if ((tok.startsWith('"') && tok.endsWith('"')) || (tok.startsWith("'") && tok.endsWith("'"))) {
        return (
          <span key={idx} className="text-emerald-300">
            {tok}
          </span>
        );
      }
      if (PYTHON_KEYWORDS.has(tok)) {
        return (
          <span key={idx} className="text-sky-400 font-medium">
            {tok}
          </span>
        );
      }
      if (/^\d[\d_]*$/.test(tok)) {
        return (
          <span key={idx} className="text-amber-300">
            {tok}
          </span>
        );
      }
      return (
        <span key={idx} className="text-slate-100">
          {tok}
        </span>
      );
    });
  }

  return <span className="text-slate-100">{line}</span>;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export const CodeViewer: React.FC<CodeViewerProps> = ({ file, globalQuery }) => {
  const [copied, setCopied] = useState(false);
  const [inFileFilter, setInFileFilter] = useState('');

  const lines = useMemo(() => file.content.split('\n'), [file.content]);
  const activeSearch = (inFileFilter || globalQuery).trim().toLowerCase();

  const matchingLineCount = useMemo(() => {
    if (!activeSearch) return 0;
    return lines.filter((l) => l.toLowerCase().includes(activeSearch)).length;
  }, [lines, activeSearch]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(file.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Fallback for clipboard restrictions
    }
  };

  const handleDownloadSingle = () => {
    const blob = new Blob([file.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = file.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      {/* File Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4 border-b border-slate-200 bg-white">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-semibold text-slate-900 font-mono truncate">{file.name}</h2>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span>{file.languageLabel}</span>
            <span aria-hidden="true">·</span>
            <span className="font-mono tabular-nums">{file.lines} lines</span>
            <span aria-hidden="true">·</span>
            <span className="font-mono tabular-nums">{formatBytes(file.bytes)}</span>
            <span aria-hidden="true">·</span>
            <span className="text-slate-600">{file.role}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={inFileFilter}
              onChange={(e) => setInFileFilter(e.target.value)}
              placeholder="Find in file..."
              aria-label="Find in file"
              className="w-44 pl-8 pr-3 py-1.5 text-xs text-slate-800 bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600"
            />
          </div>

          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-md hover:bg-slate-50 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>

          <button
            type="button"
            onClick={handleDownloadSingle}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-md hover:bg-slate-50 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download</span>
          </button>
        </div>
      </div>

      {activeSearch && (
        <div className="px-6 py-2 bg-slate-50 border-b border-slate-200 text-xs text-slate-600 flex items-center justify-between">
          <span>
            Highlighting lines matching <span className="font-mono font-medium text-slate-900">{activeSearch}</span>
          </span>
          <span className="font-mono tabular-nums text-slate-500">
            {matchingLineCount} {matchingLineCount === 1 ? 'match' : 'matches'}
          </span>
        </div>
      )}

      {/* Code Viewport */}
      <div className="flex-1 overflow-auto bg-slate-950 text-slate-100">
        <div className="py-4 min-w-max">
          {lines.map((line, index) => {
            const isMatch = activeSearch.length > 0 && line.toLowerCase().includes(activeSearch);
            return (
              <div
                key={index}
                className={`flex text-[13px] leading-6 font-mono px-4 ${
                  isMatch ? 'bg-blue-500/20' : 'hover:bg-slate-900/70'
                }`}
              >
                <span className="select-none w-11 pr-4 text-right text-slate-500 tabular-nums shrink-0">
                  {index + 1}
                </span>
                <span className="whitespace-pre">{renderHighlightedLine(line, file.language)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
