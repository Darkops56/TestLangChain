declare module 'page-flip' {
  export interface PageFlipOptions {
    width: number;
    height: number;
    size?: 'fixed' | 'stretch';
    minWidth?: number;
    maxWidth?: number;
    minHeight?: number;
    maxHeight?: number;
    maxShadowOpacity?: number;
    showCover?: boolean;
    mobileScrollSupport?: boolean;
    flippingTime?: number;
    usePortrait?: boolean;
    startZIndex?: number;
    autoSize?: boolean;
    drawShadow?: boolean;
    showPageCorners?: boolean;
    disableFlipByClick?: boolean;
    startPage?: number;
    swipeDistance?: number;
    clickEventForward?: boolean;
    useMouseEvents?: boolean;
  }

  export class PageFlip {
    constructor(element: HTMLElement, options: PageFlipOptions);
    loadFromHTML(elements: NodeListOf<Element> | HTMLElement[]): void;
    loadFromImages(images: string[]): void;
    flip(pageNum: number, corner?: string): void;
    flipNext(corner?: string): void;
    flipPrev(corner?: string): void;
    turnToPage(pageNum: number): void;
    turnToNextPage(): void;
    turnToPrevPage(): void;
    getCurrentPageIndex(): number;
    getPageCount(): number;
    getOrientation(): string;
    getState(): string;
    on(eventName: string, callback: (e: any) => void): PageFlip;
    destroy(): void;
    update(): void;
    updateFromHTML(elements: NodeListOf<Element> | HTMLElement[]): void;
    updateFromImages(images: string[]): void;
  }
}
