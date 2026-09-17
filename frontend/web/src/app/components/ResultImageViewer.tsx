import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type TouchEvent as ReactTouchEvent } from "react";
import { Expand, Download } from "lucide-react";

import { AppImage } from "@/app/components/AppImage";
import { Button } from "@/app/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/app/components/ui/dialog";
import { cn } from "@/app/components/ui/utils";

export type ViewerImage = {
  id: string;
  label: string;
  alt: string;
  src: string;
};

type PinchState = {
  startDistance: number;
  startScale: number;
  startOffsetX: number;
  startOffsetY: number;
  startMidX: number;
  startMidY: number;
};

type DragState = {
  startX: number;
  startY: number;
  startOffsetX: number;
  startOffsetY: number;
};

function MobileZoomImage({
  src,
  alt,
}: {
  src: string;
  alt: string;
}) {
  const [scale, setScale] = useState(1);
  const [offsetX, setOffsetX] = useState(0);
  const [offsetY, setOffsetY] = useState(0);
  const pinchStateRef = useRef<PinchState | null>(null);
  const dragStateRef = useRef<DragState | null>(null);

  useEffect(() => {
    setScale(1);
    setOffsetX(0);
    setOffsetY(0);
    pinchStateRef.current = null;
    dragStateRef.current = null;
  }, [src]);

  const clampOffset = (value: number, currentScale: number) => {
    if (currentScale <= 1) {
      return 0;
    }
    const maxOffset = (currentScale - 1) * 180;
    return Math.max(-maxOffset, Math.min(maxOffset, value));
  };

  const getTouchDistance = (event: ReactTouchEvent<HTMLDivElement>) => {
    const [first, second] = [event.touches[0], event.touches[1]];
    if (!first || !second) {
      return 0;
    }
    return Math.hypot(second.clientX - first.clientX, second.clientY - first.clientY);
  };

  const getTouchMidpoint = (event: ReactTouchEvent<HTMLDivElement>) => {
    const [first, second] = [event.touches[0], event.touches[1]];
    if (!first || !second) {
      return { x: 0, y: 0 };
    }
    return {
      x: (first.clientX + second.clientX) / 2,
      y: (first.clientY + second.clientY) / 2,
    };
  };

  const handleTouchStart = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length === 2) {
      const midpoint = getTouchMidpoint(event);
      pinchStateRef.current = {
        startDistance: getTouchDistance(event),
        startScale: scale,
        startOffsetX: offsetX,
        startOffsetY: offsetY,
        startMidX: midpoint.x,
        startMidY: midpoint.y,
      };
      dragStateRef.current = null;
      return;
    }

    if (event.touches.length === 1 && scale > 1) {
      const touch = event.touches[0];
      dragStateRef.current = {
        startX: touch.clientX,
        startY: touch.clientY,
        startOffsetX: offsetX,
        startOffsetY: offsetY,
      };
    }
  };

  const handleTouchMove = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (event.touches.length === 2 && pinchStateRef.current) {
      event.preventDefault();
      const currentDistance = getTouchDistance(event);
      const currentMidpoint = getTouchMidpoint(event);
      const nextScale = Math.max(
        1,
        Math.min(4, pinchStateRef.current.startScale * (currentDistance / pinchStateRef.current.startDistance)),
      );
      const midpointDeltaX = currentMidpoint.x - pinchStateRef.current.startMidX;
      const midpointDeltaY = currentMidpoint.y - pinchStateRef.current.startMidY;
      setScale(nextScale);
      setOffsetX(clampOffset(pinchStateRef.current.startOffsetX + midpointDeltaX, nextScale));
      setOffsetY(clampOffset(pinchStateRef.current.startOffsetY + midpointDeltaY, nextScale));
      return;
    }

    if (event.touches.length === 1 && dragStateRef.current && scale > 1) {
      event.preventDefault();
      const touch = event.touches[0];
      const deltaX = touch.clientX - dragStateRef.current.startX;
      const deltaY = touch.clientY - dragStateRef.current.startY;
      setOffsetX(clampOffset(dragStateRef.current.startOffsetX + deltaX, scale));
      setOffsetY(clampOffset(dragStateRef.current.startOffsetY + deltaY, scale));
    }
  };

  const handleTouchEnd = () => {
    if (scale <= 1) {
      setScale(1);
      setOffsetX(0);
      setOffsetY(0);
    }
    pinchStateRef.current = null;
    dragStateRef.current = null;
  };

  return (
    <div
      className="flex h-full w-full touch-none items-center justify-center overflow-hidden"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
    >
      <img
        src={src}
        alt={alt}
        draggable={false}
        className="h-auto max-h-[calc(100dvh-9.5rem)] w-full select-none object-contain"
        style={{
          transform: `translate3d(${offsetX}px, ${offsetY}px, 0) scale(${scale})`,
          transformOrigin: "center center",
          transition: pinchStateRef.current || dragStateRef.current ? "none" : "transform 160ms ease-out",
        }}
      />
    </div>
  );
}

type ZoomableImageCardProps = {
  src: string;
  alt: string;
  label: string;
  className?: string;
  fallbackClassName?: string;
  onOpen: () => void;
};

export function ZoomableImageCard({
  src,
  alt,
  label,
  className,
  fallbackClassName,
  onOpen,
}: ZoomableImageCardProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen();
    }
  };

  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.closest("button")) {
      return;
    }
    onOpen();
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Открыть ${label}`}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className="group relative cursor-zoom-in overflow-hidden rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-[#7A8B4A]/70 focus-visible:ring-offset-2"
    >
      <AppImage
        src={src}
        alt={alt}
        className={cn(className, "transition-transform duration-300 group-hover:scale-[1.015]")}
        fallbackClassName={fallbackClassName}
      />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-linear-to-t from-black/50 via-black/5 to-transparent opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100" />
      <div className="absolute top-3 right-3">
        <Button
          type="button"
          variant="secondary"
          size="icon"
          aria-label={`Увеличить ${label}`}
          onClick={(event) => {
            event.stopPropagation();
            onOpen();
          }}
          className="size-9 rounded-full border border-white/15 bg-black/55 text-white shadow-lg backdrop-blur-sm transition-all hover:bg-black/70 hover:text-white sm:opacity-0 sm:group-hover:opacity-100"
        >
          <Expand className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

type ResultImageViewerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  images: ViewerImage[];
  activeImageId: string | null;
  onActiveImageChange: (imageId: string) => void;
  prompt?: string | null;
  onDownload?: () => void | Promise<void>;
};

export function ResultImageViewer({
  open,
  onOpenChange,
  images,
  activeImageId,
  onActiveImageChange,
  prompt,
  onDownload,
}: ResultImageViewerProps) {
  const activeImage =
    images.find((image) => image.id === activeImageId) ||
    images[0] ||
    null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[100dvh] w-screen max-w-none gap-0 overflow-hidden border-0 bg-[#141618] p-0 text-white shadow-2xl sm:h-auto sm:max-h-[calc(100vh-2rem)] sm:w-[min(1680px,calc(100vw-2rem))] sm:max-w-[min(1680px,calc(100vw-2rem))] sm:rounded-2xl sm:border sm:border-white/10">
        <DialogTitle className="sr-only">Просмотр изображения</DialogTitle>
        <DialogDescription className="sr-only">
          Полноэкранный просмотр результата и исходных изображений.
        </DialogDescription>

        <div className="flex h-full min-h-0 flex-col overflow-hidden sm:grid sm:grid-cols-[minmax(0,1fr)_220px] lg:grid-cols-[minmax(0,1fr)_240px]">
          <div className="flex min-h-0 flex-1 items-center justify-center bg-[#0c0e10] p-0 sm:min-h-[78vh] sm:p-3 lg:min-h-[82vh] lg:p-4">
            {activeImage ? (
              <>
                <div className="block h-full w-full sm:hidden">
                  <MobileZoomImage src={activeImage.src} alt={activeImage.alt} />
                </div>
                <div className="hidden h-full w-full items-center justify-center sm:flex">
                  <AppImage
                    src={activeImage.src}
                    alt={activeImage.alt}
                    className="block h-auto w-auto max-h-[calc(100vh-3rem)] max-w-full rounded-xl object-contain"
                    fallbackClassName="flex min-h-[78vh] w-full items-center justify-center rounded-xl bg-[#1a1d20] text-center text-gray-400 lg:min-h-[82vh]"
                  />
                </div>
              </>
            ) : (
              <div className="flex min-h-[50vh] w-full items-center justify-center bg-[#1a1d20] text-gray-400 sm:min-h-[76vh] sm:rounded-xl lg:min-h-[80vh]">
                Нет изображения
              </div>
            )}
          </div>

          <aside className="flex min-h-0 shrink-0 flex-col border-t border-white/10 bg-[#171a1d] sm:border-t-0 sm:border-l">
            <div className="border-b border-white/10 px-4 py-3 sm:px-5 sm:py-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-gray-400">Просмотр</p>
                  <p className="mt-1 text-lg font-semibold text-white">
                    {activeImage?.label || "Изображение"}
                  </p>
                </div>
                {activeImage?.id === "result" && onDownload && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void onDownload()}
                    className="border-white/15 bg-white/5 text-white hover:bg-white/10 hover:text-white"
                  >
                    <Download className="h-4 w-4" />
                    Скачать
                  </Button>
                )}
              </div>

              {prompt && (
                <div className="hidden rounded-xl border border-white/10 bg-white/5 p-3 sm:block">
                  <p className="mb-1 text-[11px] uppercase tracking-[0.16em] text-gray-400">Запрос</p>
                  <p className="text-sm leading-6 text-gray-200">{prompt}</p>
                </div>
              )}
            </div>

            <div className="overflow-auto px-4 py-3 sm:flex-1 sm:px-5 sm:py-4">
              <div className="flex gap-3 overflow-x-auto pb-1 sm:block sm:space-y-3 sm:overflow-visible sm:pb-0">
                {images.map((image) => {
                  const isActive = image.id === activeImage?.id;
                  return (
                    <button
                      key={image.id}
                      type="button"
                      onClick={() => onActiveImageChange(image.id)}
                      className={cn(
                        "flex min-w-[220px] items-center gap-3 rounded-2xl border p-2 text-left transition-colors sm:w-full sm:min-w-0",
                        isActive
                          ? "border-[#7A8B4A]/70 bg-[#7A8B4A]/10"
                          : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]",
                      )}
                    >
                      <div className="h-16 w-16 shrink-0 overflow-hidden rounded-xl border border-white/10 bg-black/20">
                        <AppImage
                          src={image.src}
                          alt={image.alt}
                          className="h-full w-full object-cover"
                          fallbackClassName="flex h-full w-full items-center justify-center bg-[#1a1d20] text-gray-500"
                        />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-white">{image.label}</p>
                        <p className="mt-1 text-xs text-gray-400">
                          {isActive ? "Открыто сейчас" : "Нажмите для просмотра"}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </aside>
        </div>
      </DialogContent>
    </Dialog>
  );
}
