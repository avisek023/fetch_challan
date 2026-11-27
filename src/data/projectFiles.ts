import botPy from '../../bot.py?raw';
import browserManagerPy from '../../browser_manager.py?raw';
import domSelectorsPy from '../../dom_selectors.py?raw';
import dockerfileRaw from '../../Dockerfile?raw';
import requirementsTxt from '../../requirements.txt?raw';
import envExampleRaw from '../../.env.example?raw';
import readmeMd from '../../README.md?raw';

export interface DeliverableFile {
  id: string;
  name: string;
  language: 'python' | 'dockerfile' | 'text' | 'env' | 'markdown';
  languageLabel: string;
  role: string;
  content: string;
  lines: number;
  bytes: number;
}

function makeFile(
  id: string,
  name: string,
  language: DeliverableFile['language'],
  languageLabel: string,
  role: string,
  content: string
): DeliverableFile {
  return {
    id,
    name,
    language,
    languageLabel,
    role,
    content,
    lines: content.split('\n').length,
    bytes: new TextEncoder().encode(content).length,
  };
}

export const DELIVERABLE_FILES: DeliverableFile[] = [
  makeFile(
    'bot',
    'bot.py',
    'python',
    'Python 3.11+',
    'Async Telegram ConversationHandler (PTB v22+) and aiohttp port 8080 health server',
    botPy
  ),
  makeFile(
    'browser_manager',
    'browser_manager.py',
    'python',
    'Python 3.11+',
    'Async Playwright wrapper with stealth masking, proxy support, table parser, and PDF capture',
    browserManagerPy
  ),
  makeFile(
    'dom_selectors',
    'dom_selectors.py',
    'python',
    'Python 3.11+',
    'Centralized primary and fallback selectors for accused-challan and challan-print',
    domSelectorsPy
  ),
  makeFile(
    'dockerfile',
    'Dockerfile',
    'dockerfile',
    'Docker',
    'Playwright Python v1.58.0-noble container with pre-installed Chromium and health check',
    dockerfileRaw
  ),
  makeFile(
    'requirements',
    'requirements.txt',
    'text',
    'Pip Requirements',
    'Pinned python-telegram-bot>=22.8, playwright==1.58.0, aiohttp, python-dotenv',
    requirementsTxt
  ),
  makeFile(
    'env_example',
    '.env.example',
    'env',
    'Environment',
    'Template for TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, HEADLESS_MODE, PROXY_URL, PORT',
    envExampleRaw
  ),
  makeFile(
    'readme',
    'README.md',
    'markdown',
    'Documentation',
    'Step-by-step AI Studio to GitHub to Railway, Render, and Koyeb deployment guide',
    readmeMd
  ),
];

export interface SelectorReferenceRow {
  portal: 'accused-challan' | 'challan-print';
  group: string;
  purpose: string;
  primary: string;
  fallbacks: string[];
}

export const SELECTOR_REFERENCE: SelectorReferenceRow[] = [
  {
    portal: 'accused-challan',
    group: 'vehicle_tab',
    purpose: 'Switches lookup mode to Vehicle Number tab',
    primary: '#vehicle_no',
    fallbacks: [
      "input[type='radio'][value='vehicle_no']",
      "input[type='radio'][value='vehicle']",
      "label:has-text('Vehicle Number')",
      "a:has-text('Vehicle Number')",
    ],
  },
  {
    portal: 'accused-challan',
    group: 'vehicle_input',
    purpose: 'Accepts normalized registration string (e.g. OD02AB1234)',
    primary: '#vehicle_number',
    fallbacks: [
      '#vehicleNo',
      "input[name='vehicle_number']",
      "input[name='vehicle_no']",
      "input[placeholder*='Vehicle' i]",
    ],
  },
  {
    portal: 'accused-challan',
    group: 'captcha_image',
    purpose: 'Target element for cropped PNG screenshot sent to Telegram',
    primary: '#captcha_img',
    fallbacks: [
      '#captchaImage',
      'img#captcha',
      "img[id*='captcha' i]",
      "img[src*='captcha' i]",
    ],
  },
  {
    portal: 'accused-challan',
    group: 'captcha_refresh',
    purpose: 'Reloads CAPTCHA image in-place when user taps Refresh CAPTCHA',
    primary: '#refresh_captcha',
    fallbacks: [
      '#refreshCaptcha',
      "a[onclick*='captcha' i]",
      "button[title*='Refresh' i]",
      '.refresh-captcha',
    ],
  },
  {
    portal: 'accused-challan',
    group: 'captcha_input',
    purpose: 'Receives user CAPTCHA text reply in Stage 2',
    primary: '#captcha',
    fallbacks: [
      '#captcha_code',
      "input[name='captcha']",
      "input[placeholder*='Captcha' i]",
    ],
  },
  {
    portal: 'accused-challan',
    group: 'submit_button',
    purpose: 'Clicks Get Detail to query pending challans',
    primary: '#get_detail',
    fallbacks: [
      '#getDetail',
      "button:has-text('Get Detail')",
      "input[type='submit'][value*='Get Detail' i]",
      "button[type='submit']",
    ],
  },
  {
    portal: 'accused-challan',
    group: 'challan_table',
    purpose: 'Full-page screenshot anchor and HTML table parsed for pending IDs',
    primary: '#challan_list_table',
    fallbacks: [
      '#accused_challan_table',
      'table.dataTable',
      "table:has(th:has-text('Challan'))",
      'table.table',
    ],
  },
  {
    portal: 'challan-print',
    group: 'challan_input',
    purpose: 'Enters each queued Pending Challan Number in Stage 3',
    primary: '#challan_no',
    fallbacks: [
      '#challanNo',
      "input[name='challan_no']",
      "input[placeholder*='Challan' i]",
    ],
  },
  {
    portal: 'challan-print',
    group: 'receipt_trigger',
    purpose: 'Clicks print/PDF action if portal lists a secondary print button',
    primary: "a[href*='print-challan']",
    fallbacks: [
      "a[href*='.pdf' i]",
      "a:has-text('Challan Print')",
      "button:has-text('Print')",
      '.btn-print',
    ],
  },
  {
    portal: 'challan-print',
    group: 'pdf_embed',
    purpose: 'Detects embedded PDF iframe/object stream for direct cookie fetch',
    primary: "iframe[src*='.pdf' i]",
    fallbacks: [
      "iframe[src*='print' i]",
      "embed[type='application/pdf']",
      "object[type='application/pdf']",
    ],
  },
];
