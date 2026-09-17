import { ReactNode } from "react";
import { useScrollAnimation } from "@/app/hooks/useScrollAnimation";

interface AnimatedSectionProps {
  children: ReactNode;
  className?: string;
}

export function AnimatedSection({ children, className = "" }: AnimatedSectionProps) {
  const { ref, isVisible } = useScrollAnimation();

  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ${
        isVisible 
          ? "opacity-100 translate-y-0" 
          : "opacity-0 translate-y-8"
      } ${className}`}
    >
      {children}
    </div>
  );
}
