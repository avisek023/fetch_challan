import React, { useMemo, useState } from 'react';
import { Download, FileCode2, Search } from 'lucide-react';
import { CodeViewer } from './components/CodeViewer';
import { DeployWorkbench } from './components/DeployWorkbench';
import { SelectorsTable } from './components/SelectorsTable';
import { WorkflowSimulator } from './components/WorkflowSimulator';
import { DELIVERABLE_FILES } from './data/projectFiles';
import { buildZipBlob } from './utils/zipBuilder';

type ActiveSection = 'files' | 'workflow' | 'selectors' | 'deploy';

export default function App() {
  const [activeSection, setActiveSection] = useState<ActiveSection>('files');
  const [selectedFileId, setSelectedFileId] = useState<string>(DELIVERABLE_FILES[0].id);
  const [fileSearch, setFileSearch] = useState('');

  const filteredFiles = useMemo(() => {
    const q = fileSearch.trim().toLowerCase();
    if (!q) return DELIVERABLE_FILES;
    return DELIVERABLE_FILES.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        f.role.toLowerCase().includes(q) ||
        f.content.toLowerCase().includes(q)
    );
  }, [fileSearch]);

  const selectedFile = useMemo(() => {
    return (
      DELIVERABLE_FILES.find((f) => f.id === selectedFileId) ??
      filteredFiles[0] ??
      DELIVERABLE_FILES[0]
    );
  }, [selectedFileId, filteredFiles]);

  const totalLines = useMemo(
    () => DELIVERABLE_FILES.reduce((sum, file) => sum + file.lines, 0),
    []
  );

  const handleDownloadZip = () => {
    const zipBlob = buildZipBlob(
      DELIVERABLE_FILES.map((file) => ({
        name: file.name,
        content: file.content,
      }))
    );
    const url = URL.createObjectURL(zipBlob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'parivahan-echallan-bot.zip';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen flex flex-col bg-white text-slate-900">
      {/* Three-Zone Top Bar Contract */}
      <header className="sticky top-0 z-20 flex items-center justify-between gap-8 px-6 h-14 border-b border-slate-200 bg-white">
        <a
          href="#files"
          onClick={(e) => {
            e.preventDefault();
            setActiveSection('files');
          }}
          className="text-base font-bold tracking-tight text-slate-900 whitespace-nowrap shrink-0"
        >
          Parivahan Bot Studio
        </a>

        <nav className="flex items-center gap-6 text-sm font-medium">
          {(
            [
              ['files', 'Source Files'],
              ['workflow', 'Workflow'],
              ['selectors', 'Selectors'],
              ['deploy', 'Deploy Guide'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveSection(key)}
              className={`py-1 transition-colors whitespace-nowrap shrink-0 cursor-pointer border-b-2 ${
                activeSection === key
                  ? 'text-blue-600 border-blue-600'
                  : 'text-slate-600 border-transparent hover:text-slate-900'
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="flex items-center shrink-0">
          <button
            type="button"
            onClick={handleDownloadZip}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download ZIP</span>
          </button>
        </div>
      </header>

      {/* Workspace Body */}
      <main className="flex-1 flex flex-col min-h-0">
        {activeSection === 'files' && (
          <div className="flex-1 flex flex-col lg:flex-row min-h-[calc(100vh-3.5rem)]">
            {/* Left Sidebar File Tree */}
            <aside className="w-full lg:w-[280px] shrink-0 border-b lg:border-b-0 lg:border-r border-slate-200 bg-slate-50 flex flex-col">
              <div className="p-4 border-b border-slate-200">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs font-semibold text-slate-900">Deliverables</span>
                  <span className="text-xs text-slate-500 font-mono tabular-nums">
                    {DELIVERABLE_FILES.length} files · {totalLines} lines
                  </span>
                </div>
                <div className="mt-3 relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    type="text"
                    value={fileSearch}
                    onChange={(e) => setFileSearch(e.target.value)}
                    placeholder="Search files or code..."
                    aria-label="Search files or code"
                    className="w-full pl-8 pr-3 py-1.5 text-xs text-slate-800 bg-white border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600"
                  />
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
                {filteredFiles.length === 0 ? (
                  <div className="p-4 text-xs text-slate-500 text-center">
                    No deliverables match "{fileSearch}".
                  </div>
                ) : (
                  filteredFiles.map((file) => {
                    const isSelected = file.id === selectedFile.id;
                    return (
                      <button
                        key={file.id}
                        type="button"
                        onClick={() => setSelectedFileId(file.id)}
                        className={`w-full text-left px-3 py-2.5 rounded-md transition-colors cursor-pointer ${
                          isSelected
                            ? 'bg-white text-slate-900 border border-slate-200 shadow-2xs'
                            : 'text-slate-700 border border-transparent hover:bg-slate-200/50'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <FileCode2
                              className={`w-3.5 h-3.5 shrink-0 ${
                                isSelected ? 'text-blue-600' : 'text-slate-400'
                              }`}
                            />
                            <span className="text-xs font-mono font-medium truncate">{file.name}</span>
                          </div>
                          <span className="text-[11px] font-mono text-slate-400 tabular-nums shrink-0">
                            {file.lines}L
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-500 line-clamp-2 pl-5.5">
                          {file.role}
                        </p>
                      </button>
                    );
                  })
                )}
              </div>

              <div className="p-4 border-t border-slate-200 text-[11px] text-slate-500 space-y-1">
                <div>Python 3.11+ · PTB v22.8+ · Playwright 1.58.0</div>
                <div>Docker base: playwright/python:v1.58.0-noble</div>
              </div>
            </aside>

            {/* Main Code Editor Panel */}
            <section className="flex-1 min-w-0 flex flex-col max-h-[calc(100vh-3.5rem)]">
              <CodeViewer file={selectedFile} globalQuery={fileSearch} />
            </section>
          </div>
        )}

        {activeSection === 'workflow' && <WorkflowSimulator />}
        {activeSection === 'selectors' && <SelectorsTable />}
        {activeSection === 'deploy' && <DeployWorkbench />}
      </main>
    </div>
  );
}
