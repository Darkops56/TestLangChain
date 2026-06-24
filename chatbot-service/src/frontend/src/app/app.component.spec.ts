import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { AppComponent } from './app.component';

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideHttpClient()]
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('renders preloaded greeting bubbles', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelectorAll('.bot-bubble').length).toBeGreaterThanOrEqual(2);
    expect(compiled.textContent).toContain('Hey there! 👋');
  });

  it('renders hero title WE MAKE IT', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.hero-title')?.textContent).toContain('WE');
    expect(compiled.querySelector('.hero-title')?.textContent).toContain('MAKE');
    expect(compiled.querySelector('.hero-title')?.textContent).toContain('IT.');
  });

  it('renders services section with 6 rows', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelectorAll('.svc-row').length).toBe(6);
  });

  it('renders stats cards', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelectorAll('.stat-card').length).toBe(3);
    expect(compiled.textContent).toContain('10+');
    expect(compiled.textContent).toContain('40+');
    expect(compiled.textContent).toContain('30+');
  });

  it('renders footer', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.footer')).toBeTruthy();
    expect(compiled.textContent).toContain('© 2024 Novit Software');
  });

  describe('processBotMessage timestamp stripping', () => {
    let component: AppComponent;

    beforeEach(() => {
      const fixture = TestBed.createComponent(AppComponent);
      component = fixture.componentInstance;
    });

    it('strips leading [YYYY-MM-DD HH:mm] timestamp', () => {
      const msg = { id: '1', role: 'bot' as const, content: '[2026-03-19 12:08] Hola, ¿cómo estás?' };
      const result = (component as any).processBotMessage(msg);
      expect(result.content).toBe('Hola, ¿cómo estás?');
    });

    it('strips timestamp with seconds [YYYY-MM-DD HH:mm:ss]', () => {
      const msg = { id: '2', role: 'bot' as const, content: '[2026-03-19 12:08:30] Hello!' };
      const result = (component as any).processBotMessage(msg);
      expect(result.content).toBe('Hello!');
    });

    it('strips timestamp appearing mid-text', () => {
      const msg = { id: '3', role: 'bot' as const, content: 'Hola [2026-03-19 12:08] ¿cómo estás?' };
      const result = (component as any).processBotMessage(msg);
      expect(result.content).toBe('Hola ¿cómo estás?');
    });

    it('strips multiple timestamps', () => {
      const msg = { id: '4', role: 'bot' as const, content: '[2026-03-19 12:08] Hola [2026-03-20 14:00] mundo' };
      const result = (component as any).processBotMessage(msg);
      expect(result.content).toBe('Hola mundo');
    });

    it('does not modify user messages', () => {
      const msg = { id: '5', role: 'user' as const, content: '[2026-03-19 12:08] test' };
      const result = (component as any).processBotMessage(msg);
      expect(result.content).toBe('[2026-03-19 12:08] test');
    });

    it('does not modify text without timestamps', () => {
      const msg = { id: '6', role: 'bot' as const, content: 'Just a normal message' };
      const result = (component as any).processBotMessage(msg);
      expect(result.content).toBe('Just a normal message');
    });
  });
});
