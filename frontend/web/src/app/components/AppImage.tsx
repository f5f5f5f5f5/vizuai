import { useEffect, useMemo, useState } from "react";
import { ImageOff, RotateCw } from "lucide-react";

type AppImageProps = {
  src: string | null | undefined;
  alt: string;
  className?: string;
  fallbackClassName?: string;
  maxRetries?: number;
};

export function AppImage({
  src,
  alt,
  className = "",
  fallbackClassName,
  maxRetries = 1,
}: AppImageProps) {
  const [displaySrc, setDisplaySrc] = useState(src || "");
  const [status, setStatus] = useState<"loading" | "ready" | "error">(src ? "loading" : "error");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setDisplaySrc(src || "");
    setStatus(src ? "loading" : "error");
    setAttempt(0);
  }, [src]);

  const resolvedFallbackClassName = useMemo(
    () =>
      fallbackClassName ||
      `${className} flex items-center justify-center bg-gray-100 text-center text-gray-500`,
    [className, fallbackClassName],
  );

  const retry = () => {
    if (!src) {
      setStatus("error");
      return;
    }

    setAttempt(0);
    setStatus("loading");
    setDisplaySrc("");
    window.setTimeout(() => {
      setDisplaySrc(src);
    }, 120);
  };

  const handleError = () => {
    if (!src) {
      setStatus("error");
      return;
    }

    if (attempt < maxRetries) {
      const nextAttempt = attempt + 1;
      setAttempt(nextAttempt);
      setStatus("loading");
      setDisplaySrc("");
      window.setTimeout(() => {
        setDisplaySrc(src);
      }, 120);
      return;
    }

    setStatus("error");
  };

  if (status === "error" || !displaySrc) {
    return (
      <div className={resolvedFallbackClassName}>
        <div className="flex flex-col items-center gap-3 px-4 text-center">
          <ImageOff className="h-8 w-8 text-gray-400" />
          <p className="text-sm leading-snug text-gray-500">Не удалось загрузить изображение</p>
          <button
            type="button"
            onClick={retry}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-50"
          >
            <RotateCw className="h-4 w-4" />
            Повторить
          </button>
        </div>
      </div>
    );
  }

  return (
    <img
      key={`${displaySrc}:${attempt}`}
      src={displaySrc}
      alt={alt}
      className={className}
      onLoad={() => setStatus("ready")}
      onError={handleError}
    />
  );
}
