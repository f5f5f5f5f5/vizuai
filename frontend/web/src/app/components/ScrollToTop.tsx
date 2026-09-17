import { useState, useEffect } from "react";
import { ChevronUp } from "lucide-react";

export function ScrollToTop() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const toggleVisibility = () => {
      if (window.scrollY > 500) {
        setIsVisible(true);
      } else {
        setIsVisible(false);
      }
    };

    window.addEventListener("scroll", toggleVisibility);
    return () => window.removeEventListener("scroll", toggleVisibility);
  }, []);

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth"
    });
  };

  return (
    <>
      {isVisible && (
        <button
          onClick={scrollToTop}
          className="fixed bottom-8 right-8 bg-[#7A8B4A] text-white p-4 rounded-full shadow-lg hover:bg-[#5A6B3A] transition-all hover:scale-110 z-50"
          aria-label="Наверх"
        >
          <ChevronUp className="w-6 h-6" />
        </button>
      )}
    </>
  );
}
