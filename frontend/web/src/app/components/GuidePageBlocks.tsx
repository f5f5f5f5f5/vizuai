import type { ReactNode } from "react";
import { CheckCircle2 } from "lucide-react";

import { ZoomableImageCard } from "@/app/components/ResultImageViewer";

type GuideStepSectionProps = {
  step: string;
  title: string;
  description: string;
  tips?: string[];
  gallery: ReactNode;
};

export function GuideStepSection({
  step,
  title,
  description,
  tips = [],
  gallery,
}: GuideStepSectionProps) {
  return (
    <section className="space-y-5">
      <div className="space-y-2">
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#7A8B4A]">{step}</p>
        <h2 className="text-3xl text-[#2C3419] sm:text-4xl">{title}</h2>
        {description ? <p className="max-w-4xl text-base leading-7 text-[#5A6B3A] sm:text-lg">{description}</p> : null}
      </div>

      {gallery}

      {tips.length > 0 && (
        <div className="grid gap-3">
          {tips.map((tip) => (
            <div key={tip} className="flex items-start gap-3 rounded-2xl border border-[#E7E2CC] bg-[#F5F3E7] p-4">
              <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-[#7A8B4A]" />
              <p className="text-sm leading-7 text-[#5A6B3A]">{tip}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

type GuideShotProps = {
  imageId: string;
  src: string;
  alt: string;
  label: string;
  title: string;
  description?: string;
  imageClassName?: string;
  onOpen: (imageId: string) => void;
};

export function GuideShot({
  imageId,
  src,
  alt,
  label,
  title,
  description,
  imageClassName = "bg-[#0F1113] object-contain",
  onOpen,
}: GuideShotProps) {
  return (
    <div className="rounded-3xl border border-[#E7E2CC] bg-white p-4 shadow-sm sm:p-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="rounded-full bg-[#F5F3E7] px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[#7A8B4A]">
          {label}
        </span>
      </div>
      <ZoomableImageCard
        src={src}
        alt={alt}
        label={label}
        onOpen={() => onOpen(imageId)}
        className={`aspect-[16/9] w-full rounded-2xl border border-[#E7E2CC] ${imageClassName}`}
        fallbackClassName="flex min-h-[340px] items-center justify-center rounded-2xl border border-[#E7E2CC] bg-[#F5F3E7] text-center text-[#5A6B3A] sm:min-h-[420px]"
      />
      <div className="mt-4 space-y-1">
        <h3 className="text-xl text-[#2C3419] sm:text-2xl">{title}</h3>
        {description ? <p className="text-base leading-7 text-[#5A6B3A]">{description}</p> : null}
      </div>
    </div>
  );
}

type GuidePromptCardProps = {
  title: string;
  prompt: string;
};

export function GuidePromptCard({ title, prompt }: GuidePromptCardProps) {
  return (
    <div className="rounded-3xl border border-[#E7E2CC] bg-[#F5F3E7] p-5 sm:p-6">
      <p className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#7A8B4A]">{title}</p>
      <p className="text-base leading-7 text-[#2C3419]">{prompt}</p>
    </div>
  );
}
