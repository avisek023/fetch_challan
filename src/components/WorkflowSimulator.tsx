import React, { useState } from 'react';
import { FileText, RefreshCw, RotateCcw, Send, X } from 'lucide-react';

type SimState =
  | 'IDLE'
  | 'WAITING_FOR_VEHICLE'
  | 'WAITING_FOR_CAPTCHA_LIST'
  | 'WAITING_FOR_CAPTCHA_PRINT'
  | 'COMPLETED';

interface ChatMessage {
  id: number;
  sender: 'user' | 'bot';
  text: string;
  attachment?: 'captcha_list' | 'table_screenshot' | 'captcha_print' | 'pdf_doc';
  captchaCode?: string;
  challanLabel?: string;
  pdfName?: string;
  showInlineButtons?: boolean;
}

const SAMPLE_CHALLANS = ['OD1029384756120934', 'OD1029384756124811'];
const CAPTCHA_SEQUENCE = ['7K4M9P', 'B8N2XQ', 'W5R9TC', 'H3V6DL'];

const STAGE_SPECS = [
  {
    id: 'stage-1',
    state: 'WAITING_FOR_VEHICLE',
    title: '01. Vehicle Lookup & Stealth Browser Init',
    portal: 'echallan.parivahan.gov.in/index/accused-challan',
    handler: 'start_command -> receive_vehicle_number',
    details: [
      'Verifies Telegram sender ID against ALLOWED_USER_IDS from environment variables.',
      'Launches headless Playwright Chromium (1366x768, Windows Chrome UA, navigator.webdriver masked) and persists BrowserContext + Page in context.user_data["browser_session"].',
      'Selects Vehicle Number tab, enters normalized registration (e.g. OD02AB1234), crops CAPTCHA PNG, and sends it with Refresh CAPTCHA and Cancel inline buttons.',
    ],
  },
  {
    id: 'stage-2',
    state: 'WAITING_FOR_CAPTCHA_LIST',
    title: '02. Table Screenshot & Pending Queue Extraction',
    portal: 'Same BrowserContext & Page (cookies preserved)',
    handler: 'handle_captcha_list_reply / handle_refresh_captcha_list',
    details: [
      'Fills CAPTCHA reply and clicks Get Detail. If Invalid Captcha is detected, dismisses modal, captures a fresh CAPTCHA image, and re-prompts in place.',
      'Captures a full_page=True PNG screenshot of the pending challans table and sends it to the Telegram DM.',
      'Parses table headers and rows dynamically, skips Disposed/Paid rows, and stores every Pending Challan Number in context.user_data["challan_queue"]. Closes browser immediately if 0 pending challans exist.',
    ],
  },
  {
    id: 'stage-3',
    state: 'WAITING_FOR_CAPTCHA_PRINT',
    title: '03. Sequential PDF Receipt Download Loop',
    portal: 'echallan.parivahan.gov.in/index/challan-print',
    handler: 'handle_captcha_print_reply / _prompt_next_challan_print',
    details: [
      'Iterates through challan_queue using the existing BrowserContext so portal session cookies persist.',
      'Prompts with exact caption: Challan [1/N]: <CHALLAN_NO> — Reply with CAPTCHA to download PDF.',
      'Captures PDF via 3-tier fallback (Playwright download event -> application/pdf network stream -> Chromium page.pdf()), saves to /tmp/<CHALLAN_NO>.pdf, uploads to Telegram, and unlinks the temp file in finally.',
    ],
  },
  {
    id: 'stage-4',
    state: 'CLEANUP & HEALTH',
    title: '04. Resource Cleanup & Port 8080 Health Probe',
    portal: 'GET /health on 0.0.0.0:8080 (aiohttp)',
    handler: 'cleanup_user_session / conversation_timeout_handler / post_shutdown',
    details: [
      'Closes Page, BrowserContext, Browser, and Playwright instance inside finally blocks, on /cancel or Cancel button, and automatically after 180 seconds of inactivity.',
      'Tracks active sessions in application.bot_data["active_sessions"] so container SIGTERM shuts down Chromium cleanly without orphan processes.',
      'Runs an aiohttp server inside the PTB asyncio loop returning HTTP 200 JSON on /, /health, and /healthz for Railway, Render, and Koyeb liveness checks.',
    ],
  },
];

export const WorkflowSimulator: React.FC = () => {
  const [simState, setSimState] = useState<SimState>('WAITING_FOR_VEHICLE');
  const [vehicleNo, setVehicleNo] = useState('OD02AB1234');
  const [captchaInput, setCaptchaInput] = useState('');
  const [captchaIdx, setCaptchaIdx] = useState(0);
  const [challanIdx, setChallanIdx] = useState(0);
  const [browserOpen, setBrowserOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      sender: 'bot',
      text: 'Parivahan eChallan Assistant ready. Send a vehicle registration number (e.g. OD02AB1234) to start Stage 1.',
    },
  ]);

  const currentCaptcha = CAPTCHA_SEQUENCE[captchaIdx % CAPTCHA_SEQUENCE.length];

  const appendMessages = (newItems: Omit<ChatMessage, 'id'>[]) => {
    setMessages((prev) => {
      let nextId = prev.length > 0 ? prev[prev.length - 1].id + 1 : 1;
      return [...prev, ...newItems.map((item) => ({ ...item, id: nextId++ }))];
    });
  };

  const resetSim = () => {
    setSimState('WAITING_FOR_VEHICLE');
    setVehicleNo('OD02AB1234');
    setCaptchaInput('');
    setCaptchaIdx(0);
    setChallanIdx(0);
    setBrowserOpen(false);
    setMessages([
      {
        id: 1,
        sender: 'bot',
        text: 'Parivahan eChallan Assistant ready. Send a vehicle registration number (e.g. OD02AB1234) to start Stage 1.',
      },
    ]);
  };

  const handleSubmitVehicle = (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = vehicleNo.replace(/[\s-]+/g, '').toUpperCase();
    if (!cleaned) return;
    setVehicleNo(cleaned);
    setBrowserOpen(true);
    setSimState('WAITING_FOR_CAPTCHA_LIST');
    appendMessages([
      { sender: 'user', text: cleaned },
      {
        sender: 'bot',
        text: `Vehicle: ${cleaned} — Reply with the CAPTCHA characters shown above.`,
        attachment: 'captcha_list',
        captchaCode: currentCaptcha,
        showInlineButtons: true,
      },
    ]);
  };

  const handleRefreshCaptcha = () => {
    const nextIdx = captchaIdx + 1;
    setCaptchaIdx(nextIdx);
    const freshCode = CAPTCHA_SEQUENCE[nextIdx % CAPTCHA_SEQUENCE.length];

    if (simState === 'WAITING_FOR_CAPTCHA_LIST') {
      appendMessages([
        { sender: 'user', text: '[Clicked Refresh CAPTCHA]' },
        {
          sender: 'bot',
          text: `Refreshed CAPTCHA for ${vehicleNo}. Reply with the new characters.`,
          attachment: 'captcha_list',
          captchaCode: freshCode,
          showInlineButtons: true,
        },
      ]);
    } else if (simState === 'WAITING_FOR_CAPTCHA_PRINT') {
      const ch = SAMPLE_CHALLANS[challanIdx];
      appendMessages([
        { sender: 'user', text: '[Clicked Refresh CAPTCHA]' },
        {
          sender: 'bot',
          text: `Challan [${challanIdx + 1}/${SAMPLE_CHALLANS.length}]: ${ch} — Reply with CAPTCHA to download PDF`,
          attachment: 'captcha_print',
          captchaCode: freshCode,
          challanLabel: ch,
          showInlineButtons: true,
        },
      ]);
    }
  };

  const handleCancelFlow = (reason: 'cancel' | 'timeout') => {
    setBrowserOpen(false);
    setSimState('COMPLETED');
    appendMessages([
      ...(reason === 'cancel' ? [{ sender: 'user' as const, text: '/cancel' }] : []),
      {
        sender: 'bot',
        text:
          reason === 'timeout'
            ? 'Session timed out after 180 seconds of inactivity. BrowserContext closed cleanly.'
            : 'Operation cancelled. Playwright BrowserContext and Page closed.',
      },
    ]);
  };

  const handleSubmitCaptcha = (forceWrong = false) => {
    const submitted = forceWrong ? 'WRONG9' : (captchaInput.trim() || currentCaptcha).toUpperCase();
    setCaptchaInput('');

    if (submitted !== currentCaptcha) {
      const nextIdx = captchaIdx + 1;
      setCaptchaIdx(nextIdx);
      const freshCode = CAPTCHA_SEQUENCE[nextIdx % CAPTCHA_SEQUENCE.length];

      if (simState === 'WAITING_FOR_CAPTCHA_LIST') {
        appendMessages([
          { sender: 'user', text: submitted },
          {
            sender: 'bot',
            text: `Invalid CAPTCHA for ${vehicleNo}. Please try again with the new image above (no restart required).`,
            attachment: 'captcha_list',
            captchaCode: freshCode,
            showInlineButtons: true,
          },
        ]);
      } else if (simState === 'WAITING_FOR_CAPTCHA_PRINT') {
        const ch = SAMPLE_CHALLANS[challanIdx];
        appendMessages([
          { sender: 'user', text: submitted },
          {
            sender: 'bot',
            text: `Invalid CAPTCHA. Challan [${challanIdx + 1}/${SAMPLE_CHALLANS.length}]: ${ch} — Reply with CAPTCHA to download PDF`,
            attachment: 'captcha_print',
            captchaCode: freshCode,
            challanLabel: ch,
            showInlineButtons: true,
          },
        ]);
      }
      return;
    }

    if (simState === 'WAITING_FOR_CAPTCHA_LIST') {
      const nextIdx = captchaIdx + 1;
      setCaptchaIdx(nextIdx);
      const printCode = CAPTCHA_SEQUENCE[nextIdx % CAPTCHA_SEQUENCE.length];
      setChallanIdx(0);
      setSimState('WAITING_FOR_CAPTCHA_PRINT');

      appendMessages([
        { sender: 'user', text: submitted },
        {
          sender: 'bot',
          text: `Pending Challans for ${vehicleNo} — Extracted 2 pending challan(s) into context.user_data["challan_queue"].`,
          attachment: 'table_screenshot',
        },
        {
          sender: 'bot',
          text: `Challan [1/${SAMPLE_CHALLANS.length}]: ${SAMPLE_CHALLANS[0]} — Reply with CAPTCHA to download PDF`,
          attachment: 'captcha_print',
          captchaCode: printCode,
          challanLabel: SAMPLE_CHALLANS[0],
          showInlineButtons: true,
        },
      ]);
      return;
    }

    if (simState === 'WAITING_FOR_CAPTCHA_PRINT') {
      const completedChallan = SAMPLE_CHALLANS[challanIdx];
      const nextChallanIdx = challanIdx + 1;

      if (nextChallanIdx < SAMPLE_CHALLANS.length) {
        const nextCapIdx = captchaIdx + 1;
        setCaptchaIdx(nextCapIdx);
        setChallanIdx(nextChallanIdx);
        appendMessages([
          { sender: 'user', text: submitted },
          {
            sender: 'bot',
            text: `Uploaded ${completedChallan}.pdf and deleted /tmp/${completedChallan}.pdf in finally block.`,
            attachment: 'pdf_doc',
            pdfName: `${completedChallan}.pdf`,
          },
          {
            sender: 'bot',
            text: `Challan [${nextChallanIdx + 1}/${SAMPLE_CHALLANS.length}]: ${SAMPLE_CHALLANS[nextChallanIdx]} — Reply with CAPTCHA to download PDF`,
            attachment: 'captcha_print',
            captchaCode: CAPTCHA_SEQUENCE[nextCapIdx % CAPTCHA_SEQUENCE.length],
            challanLabel: SAMPLE_CHALLANS[nextChallanIdx],
            showInlineButtons: true,
          },
        ]);
      } else {
        setBrowserOpen(false);
        setSimState('COMPLETED');
        appendMessages([
          { sender: 'user', text: submitted },
          {
            sender: 'bot',
            text: `Uploaded ${completedChallan}.pdf and deleted /tmp/${completedChallan}.pdf in finally block.`,
            attachment: 'pdf_doc',
            pdfName: `${completedChallan}.pdf`,
          },
          {
            sender: 'bot',
            text: `Completed! All ${SAMPLE_CHALLANS.length} pending challan PDF(s) for ${vehicleNo} sent. Chromium session closed.`,
          },
        ]);
      }
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Conversation State Machine & Session Walkthrough
          </h1>
          <p className="mt-1.5 text-sm text-slate-600 max-w-2xl">
            Inspect how <span className="font-mono text-slate-800">bot.py</span> and{' '}
            <span className="font-mono text-slate-800">browser_manager.py</span> preserve cookies across all three
            ConversationHandler stages and test the Telegram flow interactively.
          </p>
        </div>
        <button
          type="button"
          onClick={resetSim}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-md hover:bg-slate-50 transition-colors cursor-pointer"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset Walkthrough</span>
        </button>
      </div>

      <div className="mt-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left: 4-Stage Architecture Breakdown */}
        <div className="lg:col-span-7 space-y-6">
          {STAGE_SPECS.map((stage) => {
            const isActive =
              (stage.state === simState) ||
              (stage.state === 'CLEANUP & HEALTH' && simState === 'COMPLETED');
            return (
              <div
                key={stage.id}
                className={`p-5 rounded-lg border transition-colors ${
                  isActive
                    ? 'border-blue-600 bg-blue-50/40'
                    : 'border-slate-200 bg-white'
                }`}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-base font-semibold text-slate-900">{stage.title}</h2>
                  <span className="text-xs font-mono text-slate-500">{stage.state}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="font-mono text-slate-700">{stage.portal}</span>
                  <span aria-hidden="true">·</span>
                  <span className="font-mono">{stage.handler}</span>
                </div>
                <ul className="mt-3 space-y-1.5 text-sm text-slate-700 list-disc pl-5">
                  {stage.details.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        {/* Right: Interactive Telegram Flow Simulator */}
        <div className="lg:col-span-5 border border-slate-200 rounded-lg bg-white overflow-hidden">
          <div className="px-5 py-3.5 border-b border-slate-200 bg-slate-50 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Telegram DM Walkthrough</h3>
              <p className="text-xs text-slate-500 mt-0.5 font-mono">
                State: {simState} · Chromium: {browserOpen ? 'Active (cookies persisted)' : 'Closed'}
              </p>
            </div>
            {browserOpen && (
              <button
                type="button"
                onClick={() => handleCancelFlow('timeout')}
                className="px-2.5 py-1 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded hover:bg-slate-100 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
              >
                Simulate 180s Timeout
              </button>
            )}
          </div>

          <div className="p-4 h-[440px] overflow-y-auto space-y-3 bg-slate-50/50">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-[88%] rounded-lg px-3.5 py-2.5 text-xs leading-relaxed border ${
                    msg.sender === 'user'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-slate-800 border-slate-200'
                  }`}
                >
                  {(msg.attachment === 'captcha_list' || msg.attachment === 'captcha_print') && (
                    <div className="mb-2 p-2.5 rounded bg-slate-900 text-slate-100 font-mono text-center tracking-[0.35em] text-sm select-all">
                      {msg.captchaCode}
                    </div>
                  )}

                  {msg.attachment === 'table_screenshot' && (
                    <div className="mb-2 border border-slate-200 rounded overflow-hidden text-[11px] font-mono">
                      <div className="bg-slate-100 px-2 py-1 text-slate-700 font-medium border-b border-slate-200">
                        full_page_screenshot.png (1366x768)
                      </div>
                      <div className="p-2 space-y-1 bg-white text-slate-700">
                        <div className="flex justify-between gap-2">
                          <span>OD1029384756120934</span>
                          <span className="text-amber-700">Pending · ₹1,000</span>
                        </div>
                        <div className="flex justify-between gap-2">
                          <span>OD1029384756124811</span>
                          <span className="text-amber-700">Pending · ₹500</span>
                        </div>
                        <div className="flex justify-between gap-2 text-slate-400 line-through">
                          <span>OD1029384756110022</span>
                          <span>Disposed (skipped)</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {msg.attachment === 'pdf_doc' && (
                    <div className="mb-2 flex items-center gap-2 p-2 rounded bg-slate-50 border border-slate-200 text-slate-800 font-mono">
                      <FileText className="w-4 h-4 text-blue-600 shrink-0" />
                      <span className="truncate">{msg.pdfName}</span>
                    </div>
                  )}

                  <p>{msg.text}</p>
                </div>

                {msg.showInlineButtons &&
                  (simState === 'WAITING_FOR_CAPTCHA_LIST' || simState === 'WAITING_FOR_CAPTCHA_PRINT') &&
                  msg.id === messages[messages.length - 1].id && (
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={handleRefreshCaptcha}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-slate-700 bg-white border border-slate-300 rounded hover:bg-slate-50 transition-colors cursor-pointer"
                      >
                        <RefreshCw className="w-3 h-3" />
                        <span>Refresh CAPTCHA</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCancelFlow('cancel')}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-rose-700 bg-white border border-slate-300 rounded hover:bg-rose-50 transition-colors cursor-pointer"
                      >
                        <X className="w-3 h-3" />
                        <span>Cancel</span>
                      </button>
                    </div>
                  )}
              </div>
            ))}
          </div>

          {/* Interactive Action Bar */}
          <div className="p-3.5 border-t border-slate-200 bg-white">
            {simState === 'WAITING_FOR_VEHICLE' && (
              <form onSubmit={handleSubmitVehicle} className="flex items-center gap-2">
                <input
                  type="text"
                  value={vehicleNo}
                  onChange={(e) => setVehicleNo(e.target.value)}
                  placeholder="Enter vehicle no (e.g. OD02AB1234)"
                  className="flex-1 px-3 py-2 text-xs font-mono text-slate-900 bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600"
                />
                <button
                  type="submit"
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Send Vehicle</span>
                </button>
              </form>
            )}

            {(simState === 'WAITING_FOR_CAPTCHA_LIST' || simState === 'WAITING_FOR_CAPTCHA_PRINT') && (
              <div className="space-y-2">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSubmitCaptcha(false);
                  }}
                  className="flex items-center gap-2"
                >
                  <input
                    type="text"
                    value={captchaInput}
                    onChange={(e) => setCaptchaInput(e.target.value)}
                    placeholder={`Type ${currentCaptcha} (or leave blank to auto-fill)`}
                    className="flex-1 px-3 py-2 text-xs font-mono text-slate-900 bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600"
                  />
                  <button
                    type="submit"
                    className="px-3.5 py-2 text-xs font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
                  >
                    Submit Valid
                  </button>
                </form>
                <div className="flex items-center justify-between text-[11px] text-slate-500">
                  <span>Expected CAPTCHA: <span className="font-mono text-slate-800">{currentCaptcha}</span></span>
                  <button
                    type="button"
                    onClick={() => handleSubmitCaptcha(true)}
                    className="text-amber-700 hover:underline font-medium cursor-pointer"
                  >
                    Test Invalid CAPTCHA Retry
                  </button>
                </div>
              </div>
            )}

            {simState === 'COMPLETED' && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-slate-600">Conversation ended and browser resources freed.</span>
                <button
                  type="button"
                  onClick={resetSim}
                  className="px-3 py-1.5 text-xs font-medium text-white bg-slate-900 rounded-md hover:bg-slate-800 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
                >
                  Start New Lookup
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
