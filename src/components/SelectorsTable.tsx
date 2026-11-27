import React, { useMemo, useState } from 'react';
import { Check, Copy, Search } from 'lucide-react';
import { SELECTOR_REFERENCE } from '../data/projectFiles';

export const SelectorsTable: React.FC = () => {
  const [portalFilter, setPortalFilter] = useState<'all' | 'accused-challan' | 'challan-print'>('all');
  const [query, setQuery] = useState('');
  const [copiedSelector, setCopiedSelector] = useState<string | null>(null);

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return SELECTOR_REFERENCE.filter((row) => {
      if (portalFilter !== 'all' && row.portal !== portalFilter) return false;
      if (!q) return true;
      return (
        row.group.toLowerCase().includes(q) ||
        row.purpose.toLowerCase().includes(q) ||
        row.primary.toLowerCase().includes(q) ||
        row.fallbacks.some((fb) => fb.toLowerCase().includes(q))
      );
    });
  }, [portalFilter, query]);

  const handleCopy = async (selector: string) => {
    try {
      await navigator.clipboard.writeText(selector);
      setCopiedSelector(selector);
      window.setTimeout(() => setCopiedSelector(null), 1500);
    } catch {
      // Ignore clipboard failures
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Centralized Selector Matrix
          </h1>
          <p className="mt-1.5 text-sm text-slate-600 max-w-2xl">
            Every Playwright locator in <span className="font-mono text-slate-800">dom_selectors.py</span> resolves an
            ordered primary-to-fallback chain so minor Parivahan DOM changes do not break automation.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-md">
            {(
              [
                ['all', 'All Portals'],
                ['accused-challan', '/accused-challan'],
                ['challan-print', '/challan-print'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setPortalFilter(key)}
                className={`px-3 py-1.5 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                  portalFilter === key
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter selectors..."
              aria-label="Filter selectors"
              className="w-52 pl-8 pr-3 py-1.5 text-xs text-slate-800 bg-white border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600"
            />
          </div>
        </div>
      </div>

      <div className="mt-6 border border-slate-200 rounded-lg overflow-hidden bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600">
                <th className="py-3 px-4">Portal</th>
                <th className="py-3 px-4">Selector Group</th>
                <th className="py-3 px-4">Primary Selector</th>
                <th className="py-3 px-4">Fallback Chain</th>
                <th className="py-3 px-4">Purpose</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs">
              {filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-10 px-4 text-center text-slate-500">
                    No selectors match your filter. Clear the search box to inspect all 10 selector groups.
                  </td>
                </tr>
              ) : (
                filteredRows.map((row) => (
                  <tr key={`${row.portal}-${row.group}`} className="hover:bg-slate-50/70">
                    <td className="py-3.5 px-4 font-mono text-slate-500 whitespace-nowrap">
                      /{row.portal}
                    </td>
                    <td className="py-3.5 px-4 font-mono font-medium text-slate-900 whitespace-nowrap">
                      {row.group}
                    </td>
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => handleCopy(row.primary)}
                        title="Click to copy selector"
                        className="inline-flex items-center gap-1.5 font-mono text-blue-700 hover:text-blue-900 cursor-pointer"
                      >
                        <span>{row.primary}</span>
                        {copiedSelector === row.primary ? (
                          <Check className="w-3 h-3 text-emerald-600" />
                        ) : (
                          <Copy className="w-3 h-3 opacity-50" />
                        )}
                      </button>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-600">
                      <div className="flex flex-wrap gap-x-2 gap-y-1">
                        {row.fallbacks.map((fb, idx) => (
                          <span key={fb} className="text-[11px]">
                            {fb}
                            {idx < row.fallbacks.length - 1 ? ' ·' : ''}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-slate-600 max-w-xs">{row.purpose}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
