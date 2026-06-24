import { CommonModule, isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { AfterViewInit, Component, computed, ElementRef, inject, NgZone, OnInit, OnDestroy, PLATFORM_ID, signal, ViewChild } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { PageFlip } from 'page-flip';

type ChatRole = 'bot' | 'user';

interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt?: string;
  audioUrl?: string;
  transcription?: string;
  failed?: boolean;
  failReason?: string;
  isVoice?: boolean;
  imageId?: string;
}

interface SlideInfo {
  id: string;
  url: string;
  title: string;
}

/** Ordered array of all slides — page order in the book */
const SLIDE_PAGES: SlideInfo[] = [
  { id: 'portada', url: 'assets/images/slides/1-portada.png', title: 'Portada — Novit Software' },
  { id: 'simple-lo-complejo', url: 'assets/images/slides/2-simple-lo-complejo.png', title: 'Hacemos simple lo complejo' },
  { id: 'que-hacemos', url: 'assets/images/slides/3-que-hacemos.png', title: 'Qué hacemos' },
  { id: 'desarrollo', url: 'assets/images/slides/4-desarrollo.png', title: 'Desarrollo de Software' },
  { id: 'consultoria', url: 'assets/images/slides/5-consultoria.png', title: 'Consultoría IT' },
  { id: 'inteligencia-artificial', url: 'assets/images/slides/6-inteligencia-artificial.png', title: 'Inteligencia Artificial' },
  { id: 'data-science', url: 'assets/images/slides/7-data-science.png', title: 'Data Science' },
  { id: 'qa-testing', url: 'assets/images/slides/8-qa-testing.png', title: 'QA & Testing' },
  { id: 'diseno-ux-ui', url: 'assets/images/slides/9-diseño-ux-ui.png', title: 'Diseño UX/UI' },
  { id: 'casos-de-exito-1', url: 'assets/images/slides/10-casos-de-exito-1.png', title: 'Casos de Éxito (1)' },
  { id: 'casos-de-exito-2', url: 'assets/images/slides/11-casos-de-exito-2.png', title: 'Casos de Éxito (2)' },
  { id: 'caso-consultatio', url: 'assets/images/slides/12-caso-consultatio.png', title: 'Caso Consultatio' },
  { id: 'caso-novopath', url: 'assets/images/slides/13-caso-novopath.png', title: 'Caso Novopath' },
  { id: 'caso-gamma', url: 'assets/images/slides/14-caso-gamma.png', title: 'Caso Gamma' },
  { id: 'caso-ebmetrics', url: 'assets/images/slides/15-caso-ebmetrics.png', title: 'Caso EBMetrics' },
  { id: 'contratapa', url: 'assets/images/slides/16-contratapa.png', title: 'Contratapa — Contacto' },
];

/** Quick lookup by id */
const IMAGE_CATALOG: Record<string, SlideInfo> = Object.fromEntries(SLIDE_PAGES.map(s => [s.id, s]));
const COVER_SLIDE = SLIDE_PAGES[0];
const BACK_COVER_SLIDE = SLIDE_PAGES[SLIDE_PAGES.length - 1];
const SLIDE_TO_PAGE_NUMBER = new Map(SLIDE_PAGES.map((slide, idx) => [slide.id, idx]));

interface ConversationCreateResponse {
  conversationId: string;
}

interface ConversationDto {
  conversationId: string;
  messages: ChatMessage[];
  metadata?: { locale: string; messageCount: number; isRateLimited: boolean };
}

interface UserMessageResponse {
  userMessage: ChatMessage;
  botMessage: ChatMessage;
  remainingMessages: number;
}

interface TranscribeResponse {
  text: string;
  confidence: number;
  durationMs: number;
}

const CONV_STORAGE_KEY = 'novit_conversation_id';
const AUTO_TTS_STORAGE_KEY = 'novit_auto_tts';

function detectLocale(text: string): string {
  const lower = ' ' + text.toLowerCase() + ' ';
  const englishWords = [' the ', ' we ', ' our ', ' you ', ' your ', ' what ', ' that ', ' this ',
    ' is ', ' are ', ' have ', ' with ', ' from ', ' about ', ' don\'t ', ' let\'s ', ' here\'s ',
    " we've ", " i'm ", " it's ", ' would ', ' could ', ' can ', ' will ',
    ' been ', ' were ', ' they ', ' their ', ' also ', ' just ', ' more ', ' some '];
  const spanishWords = [' que ', ' los ', ' las ', ' una ', ' para ', ' por ', ' con ',
    ' del ', ' como ', ' pero ', ' tiene ', ' puede ', ' hay ',
    ' todo ', ' muy ', ' nos ', ' vos ', ' sobre ', ' desde '];
  let en = 0;
  let es = 0;
  for (const w of englishWords) if (lower.includes(w)) en++;
  for (const w of spanishWords) if (lower.includes(w)) es++;
  return en >= 2 && en > es ? 'en-US' : 'es-AR';
}

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent implements OnInit, AfterViewInit, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly ngZone = inject(NgZone);
  private ttsAudio: HTMLAudioElement | null = null;
  private audioContext: AudioContext | null = null;
  private audioStream: MediaStream | null = null;
  private pcmChunks: Float32Array[] = [];
  private pendingStop = false;
  private stopRecordingTimer: ReturnType<typeof setTimeout> | null = null;
  /** Extra recording time after button release so STT captures the last word. */
  private readonly RECORDING_TAIL_MS = 300;
  private speechToken: { token: string; region: string } | null = null;
  readonly Math = Math;
  readonly MAX_MESSAGES = 30;

  readonly prompt = signal('');
  readonly isSending = signal(false);
  readonly isTyping = signal(false);
  readonly isRecording = signal(false);
  readonly isTranscribing = signal(false);
  readonly voiceError = signal<string | null>(null);
  readonly conversationId = signal<string | null>(null);
  readonly dynamicMessages = signal<ChatMessage[]>([]);
  readonly ttsPlaying = signal<string | null>(null);
  readonly autoTTS = signal(false);
  readonly showScrollIndicator = signal(false);
  readonly notebookImage = signal<SlideInfo | null>(null);
  /**
   * Notebook lifecycle states:
   *  closed   – fully hidden
   *  stowed   – only silver binding visible on the right edge
   *  cover    – book slid in, cover visible, can click to open
   *  open     – book open at a specific page (StPageFlip controls pages)
   *  closing  – cover closing animation
   *  stowing  – sliding right to stow position
   */
  readonly notebookState = signal<'closed' | 'stowed' | 'cover' | 'open' | 'closing' | 'stowing'>(
    'stowed'
  );
  /** Whether this is a desktop viewport that should auto-open the brochure */
  private readonly isDesktopViewport =
    isPlatformBrowser(this.platformId) && !window.matchMedia('(max-width: 767px)').matches;
  /** All slides as ordered book pages */
  readonly slidePages = signal<SlideInfo[]>(SLIDE_PAGES);
  readonly innerSlidePages = computed(() => this.slidePages().slice(1, -1));
  readonly coverSlide = computed(() => this.slidePages()[0] ?? COVER_SLIDE);
  readonly backCoverSlide = computed(() => this.slidePages()[this.slidePages().length - 1] ?? BACK_COVER_SLIDE);
  /** Current open page index (0-based, -1 = not on any page / cover) */
  readonly currentPageIndex = signal(-1);
  /** Timing constants for notebook animations (ms) */
  private readonly STOW_MS = 500;
  private readonly OPEN_INIT_MS = 40;
  /** Delay before auto-opening brochure on desktop so content loads fully without flash. */
  private readonly BROCHURE_AUTO_OPEN_DELAY_MS = 1000;
  /** Small delay so PageFlip has rendered before starting any automatic navigation. */
  private readonly INITIAL_FLIP_MS = 240;
  /** Step cadence slightly above flip duration for smooth sequential page-by-page motion. */
  private readonly FLIP_STEP_MS = 520;
  /** Recovery timeout used when a flip event is delayed or missed. */
  private readonly FLIP_EVENT_FALLBACK_TIMEOUT_MS = 160;
  /** Total fallback wait before forcing a new check when no flip event arrives. */
  private readonly FLIP_STEP_WITH_FALLBACK_MS = this.FLIP_STEP_MS + this.FLIP_EVENT_FALLBACK_TIMEOUT_MS;
  /** Tiny delay lets PageFlip/DOM settle before evaluating the next auto-step. */
  private readonly FLIP_EVENT_DELAY_MS = 24;
  /** Safety bound to avoid runaway loops if page state gets stuck. */
  private readonly MAX_FLIP_STEPS = 48;
  private readonly PAGE_FLIP_CORNER = 'bottom';
  private readonly OPEN_LAYOUT_SETTLE_MS = 300;
  /** Pixel threshold below which the chat is considered "at bottom". */
  private readonly SCROLL_BOTTOM_THRESHOLD = 40;
  /** Small delay so the DOM settles before the first scroll-indicator check. */
  private readonly SCROLL_CHECK_INIT_MS = 100;
  /** Remembers the last page the user was on for re-opening */
  private lastViewedPageIndex = 0;
  /** StPageFlip instance */
  private pageFlip: PageFlip | null = null;
  private flipStepTimer: number | null = null;
  private flipSequenceToken = 0;
  private autoFlipTargetPage: number | null = null;
  private autoFlipInFlight = false;
  private autoFlipStepRunner: (() => void) | null = null;
  private pageFlipOrientation: string | null = null;
  /**
   * True while pageFlip.update() is being called programmatically.
   * Prevents the resulting 'flip' event from being treated as a real page-flip completion,
   * which would otherwise reset autoFlipInFlight and corrupt the step-by-step navigation.
   */
  private isUpdatingPageFlip = false;
  private resizeRafId: number | null = null;
  /** Watches chat-flow size changes to keep the scroll indicator in sync. */
  private chatFlowRo: ResizeObserver | null = null;
  private scrollIndicatorRafId: number | null = null;
  private readonly onWindowResize = () => {
    if (!isPlatformBrowser(this.platformId)) return;
    if (this.resizeRafId !== null) return;
    this.resizeRafId = window.requestAnimationFrame(() => {
      this.resizeRafId = null;
      if (!this.pageFlip) return;
      this.isUpdatingPageFlip = true;
      this.pageFlip.update();
      this.isUpdatingPageFlip = false;
      const nextOrientation = this.pageFlip.getOrientation();
      const prevOrientation = this.pageFlipOrientation;
      this.pageFlipOrientation = nextOrientation;

      // Keep the same focused AI page when collapsing from spread (landscape) to single-page (portrait).
      if (prevOrientation === 'landscape' && nextOrientation === 'portrait') {
        const activeNotebookImage = this.notebookImage();
        const focusedAiPage = activeNotebookImage ? SLIDE_TO_PAGE_NUMBER.get(activeNotebookImage.id) : undefined;
        const pageToKeep = focusedAiPage ?? this.currentPageIndex();
        if (pageToKeep >= 0 && this.pageFlip.getCurrentPageIndex() !== pageToKeep) {
          this.pageFlip.flip(pageToKeep, this.PAGE_FLIP_CORNER);
          this.setCurrentPageFromNumber(pageToKeep);
        }
      }
    });
  };
  @ViewChild('flipBookContainer') private flipBookRef!: ElementRef<HTMLElement>;

  /** Detected UI locale — drives the language of pre-loaded messages and labels. */
  readonly uiLocale = signal<string>(
    isPlatformBrowser(this.platformId)
      ? (navigator.language?.startsWith('en') ? 'en-US' : 'es-AR')
      : 'es-AR'
  );
  readonly isEnglish = computed(() => this.uiLocale().startsWith('en'));

  /** Pre-loaded message content — locale-driven signals (no @if/@else in template). */
  readonly greetingHeading = computed(() => this.isEnglish() ? 'Hey there! 👋' : '¡Hola! 👋');
  readonly greetingBody = computed(() => this.isEnglish()
    ? 'Welcome to Novit! I\'m the AI here — your first point of contact. We specialize in artificial intelligence and custom software development. Let me tell you about us.'
    : '¡Bienvenido a Novit! Soy la IA de acá — tu primer punto de contacto. Nos especializamos en inteligencia artificial y desarrollo de software a medida. Dejame contarte sobre nosotros.');
  readonly greetingTts = computed(() => this.isEnglish()
    ? 'Welcome to Novit! I am the AI here, your first point of contact. We specialize in artificial intelligence and custom software development. Let me tell you about us.'
    : 'Bienvenido a Novit. Soy la inteligencia artificial de acá, tu primer punto de contacto. Nos especializamos en inteligencia artificial y desarrollo de software a medida. Dejame contarte sobre nosotros.');
  readonly introBody = computed(() => this.isEnglish()
    ? 'We build intelligent software — web apps, mobile apps, enterprise platforms, and AI-driven solutions. With over ten years in the market, we combine deep tech expertise with real-world AI to deliver results. Got a project in mind or questions about AI? Just type it out or hit the mic 🎙️'
    : 'Construimos software inteligente — apps web, mobile, plataformas empresariales y soluciones con IA. Con más de 10 años en el mercado, combinamos experiencia técnica con inteligencia artificial aplicada al mundo real. ¿Tenés un proyecto en mente o preguntas sobre IA? Escribilo o usá el micrófono 🎙️');
  readonly introTts = computed(() => this.isEnglish()
    ? 'We build intelligent software. Web apps, mobile apps, enterprise platforms, and AI driven solutions. With over ten years in the market, we combine deep tech expertise with real world AI to deliver results. Got a project in mind or questions about AI? Just type it out or hit the mic.'
    : 'Construimos software inteligente. Apps web, mobile, plataformas empresariales y soluciones con inteligencia artificial. Con más de 10 años en el mercado, combinamos experiencia técnica con inteligencia artificial aplicada al mundo real. Tenés un proyecto en mente o preguntas sobre inteligencia artificial? Escribilo o usá el micrófono.');

  readonly canSend = computed(() => this.prompt().trim().length > 0 && !this.isSending());
  readonly remainingMessages = signal(30);

  @ViewChild('chatFlow') private chatFlowRef!: ElementRef<HTMLElement>;

  /** Bound scroll handler for the chat flow (added outside Angular zone for perf). */
  private readonly onChatFlowScroll = () => {
    const el = this.chatFlowRef?.nativeElement;
    if (!el) return;
    const hasMore = el.scrollHeight - el.scrollTop - el.clientHeight > this.SCROLL_BOTTOM_THRESHOLD;
    const current = this.showScrollIndicator();
    if (hasMore !== current) {
      this.ngZone.run(() => this.showScrollIndicator.set(hasMore));
    }
  };

  /** Smooth-scroll the chat flow to the bottom */
  private scrollToBottom(delay = 50): void {
    const doScroll = () => {
      const el = this.chatFlowRef?.nativeElement;
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    };
    if (delay > 0) {
      setTimeout(doScroll, delay);
    } else {
      doScroll();
    }
  }

  /** Public click handler for the scroll-down indicator */
  scrollToBottomClick(): void {
    this.showScrollIndicator.set(false);
    this.scrollToBottom(0);
  }

  /** Check whether chat-flow has content below the visible area */
  private checkScrollIndicator(): void {
    const el = this.chatFlowRef?.nativeElement;
    if (!el) { this.showScrollIndicator.set(false); return; }
    const hasMore = el.scrollHeight - el.scrollTop - el.clientHeight > this.SCROLL_BOTTOM_THRESHOLD;
    this.showScrollIndicator.set(hasMore);
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    window.addEventListener('resize', this.onWindowResize);

    // Restore auto-TTS preference
    const storedAutoTTS = localStorage.getItem(AUTO_TTS_STORAGE_KEY);
    if (storedAutoTTS === 'true') this.autoTTS.set(true);

    // Restore conversation from localStorage
    const storedId = localStorage.getItem(CONV_STORAGE_KEY);
    if (storedId) {
      this.restoreConversation(storedId);
    }
  }

  ngAfterViewInit(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    const el = this.chatFlowRef?.nativeElement;
    if (el) {
      // Run outside Angular zone so scroll events don't trigger change detection
      this.ngZone.runOutsideAngular(() => {
        el.addEventListener('scroll', this.onChatFlowScroll, { passive: true });
      });

      // Re-check scroll indicator whenever the chat-flow dimensions change
      // (covers font/image load, dynamic content, and viewport changes).
      this.chatFlowRo = new ResizeObserver(() => {
        if (this.scrollIndicatorRafId !== null) return;
        this.scrollIndicatorRafId = requestAnimationFrame(() => {
          this.scrollIndicatorRafId = null;
          this.checkScrollIndicator();
        });
      });
      this.chatFlowRo.observe(el);
    }
    // Initial check after the view has rendered
    setTimeout(() => this.checkScrollIndicator(), this.SCROLL_CHECK_INIT_MS);

    // Desktop: auto-open brochure after a short delay so it renders fully before appearing
    if (this.isDesktopViewport) {
      setTimeout(() => {
        this.openNotebookAndFlipTo(0);
      }, this.BROCHURE_AUTO_OPEN_DELAY_MS);
    }
  }

  toggleAutoTTS(): void {
    const next = !this.autoTTS();
    this.autoTTS.set(next);
    if (isPlatformBrowser(this.platformId)) {
      localStorage.setItem(AUTO_TTS_STORAGE_KEY, String(next));
    }
  }

  /** Extract [IMG:slide-id] markers from bot message text (anywhere, not just end). */
  private parseImageMarker(text: string): { cleanText: string; imageId: string | null } {
    // Match all [IMG:slide-id] markers anywhere in the text (requires a valid ID)
    const allMatches = [...text.matchAll(/\[IMG:\s*([a-zA-Z0-9_-]+)\s*\]/g)];
    const imageId = allMatches.length > 0 ? allMatches[0][1] : null;
    // Strip all [IMG:...] markers (including empty ones like [IMG:]) so nothing leaks to display/TTS
    let cleanText = text
      .replace(/\[IMG:\s*[a-zA-Z0-9_-]*\s*\]/g, '')
      .replace(/\[IMG:[^\]]*$/, '')
      .trim();
    return { cleanText, imageId };
  }

  /** Strip ALL [YYYY-MM-DD HH:mm] (and optional :ss) timestamps the AI may accidentally echo anywhere in the text. */
  private stripTimestamps(text: string): string {
    return text.replace(/\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?\]\s*/g, '').trim();
  }

  /** Process a bot message: strip timestamps, image markers and attach imageId. */
  private processBotMessage(msg: ChatMessage): ChatMessage {
    if (msg.role !== 'bot') return msg;
    const stripped = this.stripTimestamps(msg.content);
    const { cleanText, imageId } = this.parseImageMarker(stripped);
    return { ...msg, content: cleanText, imageId: imageId ?? undefined };
  }

  private isSameDay(a: Date, b: Date): boolean {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  formatTimestamp(iso?: string): string {
    if (!iso) return '';
    try {
      const date = new Date(iso);
      if (isNaN(date.getTime())) return '';

      const now = new Date();
      const yesterday = new Date(now);
      yesterday.setDate(yesterday.getDate() - 1);

      const hours = date.getHours();
      const minutes = date.getMinutes().toString().padStart(2, '0');
      const ampm = hours >= 12 ? 'pm' : 'am';
      const h12 = hours % 12 || 12;
      const time = `${h12}:${minutes}${ampm}`;

      const en = this.isEnglish();

      if (this.isSameDay(date, now)) return `${en ? 'today' : 'hoy'} ${time}`;
      if (this.isSameDay(date, yesterday)) return `${en ? 'yesterday' : 'ayer'} ${time}`;

      const day = date.getDate().toString().padStart(2, '0');
      const monthNames = en
        ? ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        : ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
      const mon = monthNames[date.getMonth()];
      const yr = (date.getFullYear() % 100).toString().padStart(2, '0');

      return `${day}-${mon}-${yr} ${time}`;
    } catch {
      return '';
    }
  }

  /** AI triggers: open the book and navigate to the requested slide. */
  private showNotebookImage(imageId: string): void {
    const slide = IMAGE_CATALOG[imageId];
    if (!slide) return;
    const pageNumber = SLIDE_TO_PAGE_NUMBER.get(imageId);
    if (pageNumber === undefined) return;

    this.notebookImage.set(slide);

    const state = this.notebookState();
    if (state === 'closed' || state === 'stowed' || state === 'cover') {
      this.openNotebookAndFlipTo(pageNumber);
    } else if (state === 'open') {
      this.flipByStepsTo(pageNumber);
    }
  }

  /** Open the book and then navigate to a specific content page. */
  private openNotebookAndFlipTo(pageNumber: number): void {
    this.notebookState.set('open');
    this.setCurrentPageFromNumber(pageNumber);
    // Wait for DOM to render then initialize StPageFlip
    setTimeout(() => {
      this.initPageFlip();
      setTimeout(() => {
        this.isUpdatingPageFlip = true;
        this.pageFlip?.update();
        this.isUpdatingPageFlip = false;
      }, this.OPEN_LAYOUT_SETTLE_MS);
      // Flip to the target page after initialization
      if (this.pageFlip && pageNumber > 0) {
        setTimeout(() => {
          this.flipByStepsTo(pageNumber);
        }, this.INITIAL_FLIP_MS);
      }
    }, this.OPEN_INIT_MS);
  }

  private setCurrentPageFromNumber(pageNumber: number): void {
    const clamped = this.clampToValidPageIndex(pageNumber);
    this.currentPageIndex.set(clamped);
    this.lastViewedPageIndex = clamped;
  }

  private clearFlipStepTimer(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    this.flipSequenceToken++;
    this.clearAutoFlipState();
    if (this.flipStepTimer !== null) {
      window.clearTimeout(this.flipStepTimer);
      this.flipStepTimer = null;
    }
  }

  private clearAutoFlipState(): void {
    this.autoFlipTargetPage = null;
    this.autoFlipInFlight = false;
    this.autoFlipStepRunner = null;
  }

  private clampToValidPageIndex(pageNumber: number): number {
    return Math.max(0, Math.min(pageNumber, SLIDE_PAGES.length - 1));
  }

  private flipByStepsTo(targetPage: number): void {
    if (!isPlatformBrowser(this.platformId) || !this.pageFlip) return;
    this.clearFlipStepTimer();
    const sequenceToken = this.flipSequenceToken;
    this.autoFlipTargetPage = this.clampToValidPageIndex(targetPage);
    let steps = 0;

    const step = (): void => {
      if (!this.pageFlip || sequenceToken !== this.flipSequenceToken) return;
      if (this.autoFlipInFlight) return;
      const target = this.autoFlipTargetPage;
      if (target === null) return;
      const current = this.pageFlip.getCurrentPageIndex();
      // In portrait mode each spread is exactly 1 page, so current === target is sufficient.
      // In landscape mode PageFlip reports the LEFT page of the spread; if the target is the
      // RIGHT page of the current spread (current + 1 === target) the desired slide is already
      // visible — stop here instead of overshooting to the next spread.
      // Guard current > 0: with showCover:true the cover occupies spread [0] alone (no right
      // page), so current=0 with target=1 must NOT stop early — page 1 is not yet visible.
      const inLandscape = this.pageFlip.getOrientation() !== 'portrait';
      const atTarget = current === target || (inLandscape && current > 0 && current + 1 === target);
      if (atTarget) {
        this.clearAutoFlipState();
        this.flipStepTimer = null;
        this.setCurrentPageFromNumber(target);
        return;
      }
      if (steps >= this.MAX_FLIP_STEPS) {
        console.warn('[Brochure] Reached max step flips, forcing direct jump to target page.');
        this.clearAutoFlipState();
        this.pageFlip.flip(target, this.PAGE_FLIP_CORNER);
        this.setCurrentPageFromNumber(target);
        return;
      }
      steps++;
      this.autoFlipInFlight = true;

      if (current < target) {
        this.pageFlip.flipNext(this.PAGE_FLIP_CORNER);
      } else {
        this.pageFlip.flipPrev(this.PAGE_FLIP_CORNER);
      }

      this.flipStepTimer = window.setTimeout(() => {
        if (sequenceToken !== this.flipSequenceToken) return;
        if (!this.autoFlipInFlight) return;
        this.autoFlipInFlight = false;
        step();
      }, this.FLIP_STEP_WITH_FALLBACK_MS);
    };

    this.autoFlipStepRunner = step;
    step();
  }

  /** Initialize StPageFlip on the flipbook container */
  private initPageFlip(): void {
    if (!isPlatformBrowser(this.platformId)) return;

    if (this.pageFlip) {
      this.pageFlip.destroy();
      this.pageFlip = null;
    }
    const el = this.flipBookRef?.nativeElement;
    if (!el) return;
    const isMobileViewport = window.matchMedia('(max-width: 767px)').matches;
    // Mobile: compute page size from available viewport to maximize image visibility
    const A4_RATIO = 297 / 210;
    let mobilePageW: number;
    if (isMobileViewport) {
      const containerPadding = 4;   // 2px left + 2px right from .notebook-panel padding
      const navAndCloseHeight = 38; // compact nav (~26px) + gap (4px) + close btn area (~8px)
      const availW = window.innerWidth - containerPadding;
      const availH = window.innerHeight * 0.65 - navAndCloseHeight; // 65dvh minus controls
      const fitByH = Math.floor(availH / A4_RATIO); // max width that fits available height
      mobilePageW = Math.min(availW, fitByH);
      mobilePageW = Math.max(mobilePageW, 200); // minimum floor
    } else {
      mobilePageW = 0; // not used in desktop path
    }
    const minWidth = isMobileViewport ? mobilePageW : 320;
    const minHeight = Math.round(minWidth * A4_RATIO);
    const maxWidth = isMobileViewport ? mobilePageW : 1200;
    const maxHeight = Math.round(maxWidth * A4_RATIO);

    this.pageFlip = new PageFlip(el, {
      width: isMobileViewport ? mobilePageW : 1000,
      height: isMobileViewport ? Math.round(mobilePageW * A4_RATIO) : 1414, // A4 ratio: 210/297
      size: isMobileViewport ? 'fixed' : 'stretch',
      minWidth,
      maxWidth,
      minHeight,
      maxHeight,
      maxShadowOpacity: 0.6,
      showCover: true,
      mobileScrollSupport: false,
      flippingTime: 460,
      usePortrait: true,
      startZIndex: 0,
      autoSize: true,
      drawShadow: true,
      showPageCorners: true,
      disableFlipByClick: false,
    });

    this.pageFlip.loadFromHTML(document.querySelectorAll('.stpf-page'));
    this.pageFlipOrientation = this.pageFlip.getOrientation();

    this.pageFlip.on('flip', (e: { data: number }) => {
      this.setCurrentPageFromNumber(e.data);
      // Ignore flip events that originate from programmatic pageFlip.update() calls.
      // Those are triggered by pages.show() inside update() and do not represent a real
      // flip animation completion; treating them as such would reset autoFlipInFlight
      // mid-animation and corrupt the step-by-step navigation sequence.
      if (this.isUpdatingPageFlip) return;
      if (!this.autoFlipStepRunner) return;
      if (this.autoFlipTargetPage === null) return;
      if (!this.autoFlipInFlight) return;
      this.autoFlipInFlight = false;
      if (this.flipStepTimer !== null) {
        window.clearTimeout(this.flipStepTimer);
        this.flipStepTimer = null;
      }
      this.flipStepTimer = window.setTimeout(() => {
        this.autoFlipStepRunner?.();
      }, this.FLIP_EVENT_DELAY_MS);
    });
  }

  /** User clicks next/prev page arrows. */
  flipPageForward(): void {
    if (this.pageFlip) {
      this.pageFlip.flipNext(this.PAGE_FLIP_CORNER);
    }
  }

  flipPageBackward(): void {
    if (this.pageFlip) {
      this.pageFlip.flipPrev(this.PAGE_FLIP_CORNER);
    }
  }

  /** Close the book: stow (slide right). */
  closeNotebook(): void {
    this.clearFlipStepTimer();
    this.notebookState.set('stowing');
    this.currentPageIndex.set(-1);
    setTimeout(() => {
      if (this.pageFlip) {
        this.pageFlip.destroy();
        this.pageFlip = null;
      }
      this.pageFlipOrientation = null;
      this.notebookState.set('stowed');
    }, this.STOW_MS);
  }

  /** Click on the stowed spine → open flipbook directly at the last viewed page. */
  unstowNotebook(): void {
    if (this.notebookState() !== 'stowed') return;
    this.openNotebookAndFlipTo(this.lastViewedPageIndex);
  }

  /** Click on the cover → open the book to the last viewed page. */
  openNotebookFromCover(): void {
    if (this.notebookState() !== 'cover') return;
    this.openNotebookAndFlipTo(this.lastViewedPageIndex);
  }

  ngOnDestroy(): void {
    this.clearFlipStepTimer();
    if (this.stopRecordingTimer !== null) {
      clearTimeout(this.stopRecordingTimer);
      this.stopRecordingTimer = null;
    }
    if (isPlatformBrowser(this.platformId)) {
      window.removeEventListener('resize', this.onWindowResize);
      const chatEl = this.chatFlowRef?.nativeElement;
      if (chatEl) chatEl.removeEventListener('scroll', this.onChatFlowScroll);
      if (this.chatFlowRo) {
        this.chatFlowRo.disconnect();
        this.chatFlowRo = null;
      }
      if (this.scrollIndicatorRafId !== null) {
        cancelAnimationFrame(this.scrollIndicatorRafId);
        this.scrollIndicatorRafId = null;
      }
      if (this.resizeRafId !== null) {
        window.cancelAnimationFrame(this.resizeRafId);
        this.resizeRafId = null;
      }
    }
    if (this.pageFlip) {
      this.pageFlip.destroy();
      this.pageFlip = null;
    }
    this.pageFlipOrientation = null;
  }

  private async restoreConversation(id: string): Promise<void> {
    try {
      const conv = await firstValueFrom(this.http.get<ConversationDto>(`/api/chat/conversations/${id}`));
      this.conversationId.set(conv.conversationId);
      if (conv.messages && conv.messages.length > 0) {
        // Detect trailing user messages with no bot reply — these were likely rate-limited
        const msgs = [...conv.messages];
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === 'user') {
            msgs[i] = { ...msgs[i], failed: true, failReason: 'Not sent — tap ↻ to retry' };
          } else {
            break; // stop at the last bot message
          }
        }
        // Process bot messages to extract image markers
        const processed = msgs.map(m => this.processBotMessage(m));
        this.dynamicMessages.set(processed);
        this.scrollToBottom();
        // Update remaining messages from metadata
        if (conv.metadata) {
          this.remainingMessages.set(Math.max(0, this.MAX_MESSAGES - (conv.metadata.messageCount || 0)));
        }
      }
    } catch {
      // Conversation expired or not found — clear stale ID
      localStorage.removeItem(CONV_STORAGE_KEY);
    }
  }

  async sendPrompt(event: Event): Promise<void> {
    event.preventDefault();
    const text = this.prompt().trim();
    if (!text || this.isSending()) {
      return;
    }

    this.isSending.set(true);
    const tempUserId = `user-${Date.now()}`;
    try {
      const id = await this.ensureConversation();

      // Add user message immediately
      const tempUserMsg: ChatMessage = { id: tempUserId, role: 'user', content: text, createdAt: new Date().toISOString() };
      this.dynamicMessages.update(m => [...m, tempUserMsg]);
      this.prompt.set('');
      this.scrollToBottom();

      // Show typing indicator
      this.isTyping.set(true);
      this.scrollToBottom();

      const response = await firstValueFrom(this.http.post<UserMessageResponse>(`/api/chat/conversations/${id}/messages`, {
        text,
        locale: detectLocale(text)
      }));

      this.isTyping.set(false);

      // Replace temp user message with real one, add bot message
      const botMsg = this.processBotMessage(response.botMessage);

      this.dynamicMessages.update(msgs => {
        const updated = msgs.map(m => m.id === tempUserId ? { ...m, id: response.userMessage.id, createdAt: response.userMessage.createdAt } : m);
        return [...updated, botMsg];
      });
      if (botMsg.imageId) this.showNotebookImage(botMsg.imageId);
      this.remainingMessages.set(response.remainingMessages);
      this.scrollToBottom();

      // Auto-play TTS for bot response if enabled
      if (this.autoTTS() && response.botMessage) {
        this.playTTS(botMsg.content, response.botMessage.id);
      }
    } catch (e: any) {
      this.isTyping.set(false);
      const status = e?.status ?? e?.error?.status;
      const savedId = e?.error?.savedMessageId;
      if (status === 429) {
        this.dynamicMessages.update(msgs =>
          msgs.map(m => m.id === tempUserId ? { ...m, id: savedId || m.id, failed: true, failReason: 'Message limit reached' } : m)
        );
        this.remainingMessages.set(0);
      } else {
        this.dynamicMessages.update(msgs =>
          msgs.map(m => m.id === tempUserId ? { ...m, failed: true, failReason: 'Failed to send' } : m)
        );
      }
    } finally {
      this.isSending.set(false);
      this.isTyping.set(false);
    }
  }

  async startRecording(): Promise<void> {
    if (!isPlatformBrowser(this.platformId) || this.isRecording()) return;

    this.voiceError.set(null);
    this.pendingStop = false;

    // Cancel any pending delayed stop from a previous recording
    if (this.stopRecordingTimer !== null) {
      clearTimeout(this.stopRecordingTimer);
      this.stopRecordingTimer = null;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      this.voiceError.set('Voice recording requires a secure connection (HTTPS).');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1 } });

      // User released the button while waiting for mic permission
      if (this.pendingStop) {
        this.pendingStop = false;
        stream.getTracks().forEach(t => t.stop());
        return;
      }

      const audioContext = new AudioContext({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const pcmChunks: Float32Array[] = [];

      processor.onaudioprocess = (e) => {
        pcmChunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      this.audioContext = audioContext;
      this.audioStream = stream;
      this.pcmChunks = pcmChunks;
      this.isRecording.set(true);

      // Haptic feedback on mobile when recording starts
      if ('vibrate' in navigator) {
        navigator.vibrate(50);
      }

      // Pre-fetch speech token for faster transcription
      this.ensureSpeechToken();
    } catch (err) {
      this.pendingStop = false;
      this.isRecording.set(false);
      const domErr = err as DOMException;
      if (domErr?.name === 'NotAllowedError' || domErr?.name === 'PermissionDeniedError') {
        this.voiceError.set('Microphone access denied. Please allow microphone access.');
      } else if (domErr?.name === 'NotFoundError' || domErr?.name === 'DevicesNotFoundError') {
        this.voiceError.set('No microphone found.');
      } else {
        this.voiceError.set('Could not access microphone.');
      }
    }
  }

  private async ensureSpeechToken(): Promise<void> {
    if (this.speechToken) return;
    try {
      this.speechToken = await firstValueFrom(
        this.http.get<{ token: string; region: string }>('/api/voice/token')
      );
    } catch (e) {
      console.warn('Could not fetch speech token, will use backend proxy:', e);
    }
  }

  stopRecording(): void {
    if (!this.isRecording()) {
      // Recording hasn't started yet (getUserMedia still resolving) — flag it
      this.pendingStop = true;
      return;
    }

    // Already scheduled a delayed stop — don't schedule another
    if (this.stopRecordingTimer !== null) return;

    // Keep recording briefly so STT captures the last word
    this.stopRecordingTimer = setTimeout(() => {
      this.stopRecordingTimer = null;
      this.finalizeRecording();
    }, this.RECORDING_TAIL_MS);
  }

  private finalizeRecording(): void {
    this.isRecording.set(false);

    const stream = this.audioStream;
    const context = this.audioContext;
    const chunks = this.pcmChunks;

    if (stream) stream.getTracks().forEach(t => t.stop());
    if (context) context.close();

    this.audioStream = null;
    this.audioContext = null;
    this.pcmChunks = [];

    if (chunks && chunks.length > 0) {
      const wavBlob = this.pcmToWav(chunks, 16000);
      this.sendVoiceMessage(wavBlob);
    }
  }

  /** Resend a failed message */
  async resendMessage(msg: ChatMessage): Promise<void> {
    if (this.isSending() || this.remainingMessages() <= 0) return;

    const text = msg.content || msg.transcription || '';
    if (!text) return;

    // Clear failure state
    this.dynamicMessages.update(msgs =>
      msgs.map(m => m.id === msg.id ? { ...m, failed: false, failReason: undefined } : m)
    );

    this.isSending.set(true);
    this.isTyping.set(true);
    try {
      const id = await this.ensureConversation();
      const response = await firstValueFrom(this.http.post<UserMessageResponse>(`/api/chat/conversations/${id}/messages`, {
        text,
        locale: detectLocale(text)
      }));
      this.isTyping.set(false);
      const botMsg = this.processBotMessage(response.botMessage);
      this.dynamicMessages.update(msgs => {
        const updated = msgs.map(m => m.id === msg.id ? { ...m, id: response.userMessage.id, failed: false, createdAt: response.userMessage.createdAt } : m);
        return [...updated, botMsg];
      });
      if (botMsg.imageId) this.showNotebookImage(botMsg.imageId);
      this.remainingMessages.set(response.remainingMessages);
      this.scrollToBottom();
      // Auto-play TTS for bot response if enabled
      if (this.autoTTS() && response.botMessage) {
        this.playTTS(botMsg.content, response.botMessage.id);
      }
    } catch (e: any) {
      this.isTyping.set(false);
      const status = e?.status ?? e?.error?.status;
      this.dynamicMessages.update(msgs =>
        msgs.map(m => m.id === msg.id ? { ...m, failed: true, failReason: status === 429 ? 'Message limit reached' : 'Failed to send' } : m)
      );
      if (status === 429) this.remainingMessages.set(0);
    } finally {
      this.isSending.set(false);
      this.isTyping.set(false);
    }
  }

  private async sendVoiceMessage(blob: Blob): Promise<void> {
    this.isTranscribing.set(true);
    this.voiceError.set(null);
    const tempId = `voice-${Date.now()}`;
    try {
      const id = await this.ensureConversation();
      const audioUrl = URL.createObjectURL(blob);
      const tempUserMsg: ChatMessage = {
        id: tempId,
        role: 'user',
        content: '',
        createdAt: new Date().toISOString(),
        audioUrl,
        transcription: '...'
      };
      this.dynamicMessages.update(m => [...m, tempUserMsg]);
      this.scrollToBottom();
      let text = '';
      if (this.speechToken) {
        try {
          text = await this.transcribeDirectAzure(blob);
        } catch (e) {
          console.warn('Direct Azure STT failed, falling back to backend:', e);
          this.speechToken = null;
        }
      }

      // Fallback to backend proxy transcription
      if (!text) {
        const formData = new FormData();
        formData.append('audio', blob, 'recording.wav');
        formData.append('locale', 'es-AR');

        const transcription = await firstValueFrom(
          this.http.post<TranscribeResponse>('/api/voice/transcribe', formData)
        );
        text = transcription.text || '';
      }

      if (!text) {
        text = 'No speech detected';
      }

      // Update the temp message transcription
      this.dynamicMessages.update(msgs =>
        msgs.map(m => m.id === tempId ? { ...m, transcription: text } : m)
      );

      if (text === 'No speech detected') {
        this.voiceError.set('No speech detected. Try again.');
        return;
      }

      // Show typing indicator while waiting for AI
      this.isTyping.set(true);
      this.scrollToBottom();
      const response = await firstValueFrom(this.http.post<UserMessageResponse>(`/api/chat/conversations/${id}/messages`, {
        text,
        locale: detectLocale(text),
        isVoice: true
      }));

      this.isTyping.set(false);

      // Update user message with real ID, add bot message
      const botMsg = this.processBotMessage(response.botMessage);

      this.dynamicMessages.update(msgs => {
        const updated = msgs.map(m => m.id === tempId ? { ...m, id: response.userMessage.id, content: text, createdAt: response.userMessage.createdAt } : m);
        return [...updated, botMsg];
      });
      if (botMsg.imageId) this.showNotebookImage(botMsg.imageId);
      this.remainingMessages.set(response.remainingMessages);
      this.scrollToBottom();

      // Auto-play TTS for bot response if enabled
      if (this.autoTTS() && response.botMessage) {
        this.playTTS(botMsg.content, response.botMessage.id);
      }
    } catch (e: any) {
      console.error('Voice message failed:', e);
      this.isTyping.set(false);
      const status = e?.status ?? e?.error?.status;
      const savedId = e?.error?.savedMessageId;
      // Keep the audio bubble visible but mark as failed
      this.dynamicMessages.update(msgs =>
        msgs.map(m => m.id === tempId ? {
          ...m,
          id: savedId || m.id,
          failed: true,
          failReason: status === 429 ? 'Message limit reached' : 'Voice message failed',
          transcription: m.transcription === '...' ? undefined : m.transcription
        } : m)
      );
      if (status === 429) this.remainingMessages.set(0);
      this.voiceError.set(status === 429 ? 'Message limit reached.' : 'Voice message failed. Try typing instead.');
    } finally {
      this.isTranscribing.set(false);
    }
  }

  private pcmToWav(chunks: Float32Array[], sampleRate: number): Blob {
    let totalLength = 0;
    for (const c of chunks) totalLength += c.length;
    const pcm = new Float32Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      pcm.set(chunk, offset);
      offset += chunk.length;
    }
    const int16 = new Int16Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) {
      const s = Math.max(-1, Math.min(1, pcm[i]));
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    const header = new ArrayBuffer(44);
    const v = new DataView(header);
    const dataSize = int16.length * 2;
    this.wavStr(v, 0, 'RIFF');
    v.setUint32(4, 36 + dataSize, true);
    this.wavStr(v, 8, 'WAVE');
    this.wavStr(v, 12, 'fmt ');
    v.setUint32(16, 16, true);
    v.setUint16(20, 1, true);
    v.setUint16(22, 1, true);
    v.setUint32(24, sampleRate, true);
    v.setUint32(28, sampleRate * 2, true);
    v.setUint16(32, 2, true);
    v.setUint16(34, 16, true);
    this.wavStr(v, 36, 'data');
    v.setUint32(40, dataSize, true);
    return new Blob([header, int16.buffer], { type: 'audio/wav' });
  }

  private wavStr(view: DataView, offset: number, str: string): void {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  }

  /** Run one-shot recognition with Speech SDK, returns recognized text. */
  private async transcribeDirectAzure(blob: Blob): Promise<string> {
    const token = this.speechToken!;
    const url = `https://${token.region}.stt.speech.microsoft.com/speech/recognition/dictation/cognitiveservices/v1?language=es-AR&format=detailed&profanity=raw`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token.token}`,
        'Content-Type': 'audio/wav; codecs=audio/pcm; samplerate=16000',
        'Accept': 'application/json'
      },
      body: blob
    });

    if (!response.ok) {
      throw new Error(`Azure STT returned ${response.status}`);
    }

    const result = await response.json();
    if (result.RecognitionStatus === 'Success') {
      return result.DisplayText || '';
    }
    return '';
  }

  private async ensureConversation(): Promise<string> {
    const existing = this.conversationId();
    if (existing) {
      return existing;
    }

    const created = await firstValueFrom(this.http.post<ConversationCreateResponse>('/api/chat/conversations', {
      locale: 'en-US'
    }));

    this.conversationId.set(created.conversationId);
    if (isPlatformBrowser(this.platformId)) {
      localStorage.setItem(CONV_STORAGE_KEY, created.conversationId);
    }
    return created.conversationId;
  }

  async playTTS(text: string, messageId: string): Promise<void> {
    if (this.ttsPlaying() === messageId) {
      this.stopTTS();
      return;
    }

    this.stopTTS();
    this.ttsPlaying.set(messageId);

    try {
      const locale = detectLocale(text);
      const blob = await firstValueFrom(
        this.http.post('/api/voice/synthesize', {
          text,
          locale,
          messageId
        }, { responseType: 'blob' })
      );

      const url = URL.createObjectURL(blob);
      this.ttsAudio = new Audio(url);
      this.ttsAudio.onended = () => {
        this.ttsPlaying.set(null);
        URL.revokeObjectURL(url);
      };
      this.ttsAudio.onerror = () => {
        this.ttsPlaying.set(null);
        URL.revokeObjectURL(url);
      };
      await this.ttsAudio.play();
    } catch {
      this.ttsPlaying.set(null);
    }
  }

  private stopTTS(): void {
    if (this.ttsAudio) {
      this.ttsAudio.pause();
      this.ttsAudio = null;
    }
    this.ttsPlaying.set(null);
  }

  /** Simple markdown-to-HTML renderer for bot messages. */
  renderMarkdown(text: string): SafeHtml {
    if (!text) return '';
    let html = text
      // Escape HTML
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // Bold: **text** or __text__ (must be processed before italic)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/__(.+?)__/g, '<strong>$1</strong>')
      // Italic: *text* or _text_ (use negative lookbehind/ahead to avoid matching ** remnants)
      .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
      .replace(/(?<!_)_(?!_)(.+?)(?<!_)_(?!_)/g, '<em>$1</em>')
      // Inline code: `code`
      .replace(/`(.+?)`/g, '<code>$1</code>')
      // Unordered list items: - item (at line start, not * to avoid conflict)
      .replace(/^[\s]*-\s+(.+)$/gm, '<li>$1</li>')
      // Headings (strip, just bold)
      .replace(/^#{1,6}\s+(.+)$/gm, '<strong>$1</strong>')
      // Line breaks
      .replace(/\n/g, '<br>');
    // Wrap consecutive <li> in <ul>
    html = html.replace(/(<li>.*?<\/li>(?:<br>)?)+/g, (match) =>
      '<ul>' + match.replace(/<br>/g, '') + '</ul>'
    );
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
