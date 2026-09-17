import { Instagram, Send, Mail } from "lucide-react";
import { Link } from "react-router";
import { useLocale } from "@/app/i18n";
import { trackPublicClick } from "@/app/lib/analytics/client";

export function Footer() {
  const { isEnglish, publicPath } = useLocale();
  const footerLinks = [
    { href: "/faq", label: "FAQ" },
    { href: "/pricing", label: isEnglish ? "Pricing" : "Цены" },
    { href: "/examples", label: isEnglish ? "Examples" : "Примеры" },
    { href: "/how-it-works", label: isEnglish ? "How it works" : "Как это работает" },
    { href: "/interior-design-from-photo", label: isEnglish ? "Design from photo" : "Дизайн по фото" },
    { href: "/design-by-reference", label: isEnglish ? "Design by reference" : "Дизайн по референсу" },
    { href: "/furniture-search-by-photo", label: isEnglish ? "Furniture search" : "Подбор мебели по фото" },
  ];

  return (
    <footer className="bg-[#5A6B3A] text-white py-16 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row justify-between items-center gap-8">
          <div className="text-center md:text-left">
            <h3 className="text-2xl mb-2">VizuAI</h3>
          </div>

          <div className="flex flex-col sm:flex-row gap-4">
            <a 
              href="https://example.com/support" 
              target="_blank" 
              rel="noopener noreferrer"
              onClick={() => {
                void trackPublicClick("landing", "footer_telegram_click");
              }}
              className="flex items-center gap-2 px-6 py-3 rounded-full bg-white text-[#2C3419] hover:bg-white/95 transition-colors shadow-md font-semibold"
            >
              <Send className="w-5 h-5" />
              <span>Telegram</span>
            </a>
            <a 
              href="https://www.instagram.com/vizuai_bot" 
              target="_blank" 
              rel="noopener noreferrer"
              onClick={() => {
                void trackPublicClick("landing", "footer_instagram_click");
              }}
              className="flex items-center gap-2 px-6 py-3 rounded-full bg-white text-[#2C3419] hover:bg-white/95 transition-colors shadow-md font-semibold"
            >
              <Instagram className="w-5 h-5" />
              <span>Instagram</span>
            </a>
            <a 
              href="mailto:owner@vizuai.example" 
              onClick={() => {
                void trackPublicClick("landing", "footer_email_click");
              }}
              className="flex items-center gap-2 px-6 py-3 rounded-full bg-white text-[#2C3419] hover:bg-white/95 transition-colors shadow-md font-semibold"
            >
              <Mail className="w-5 h-5" />
              <span>owner@vizuai.example</span>
            </a>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-white/20 text-center text-white/70 text-sm space-y-2">
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
            {footerLinks.map((item) => (
              <Link
                key={item.href}
                to={publicPath(item.href)}
                onClick={() => {
                  void trackPublicClick("landing", "footer_page_click", { target: item.href });
                }}
                className="text-white/70 hover:text-white transition-colors underline"
              >
                {item.label}
              </Link>
            ))}
          </div>
          <div>
            <Link
              to={publicPath("/legal")}
              onClick={() => {
                void trackPublicClick("landing", "footer_legal_click");
              }}
              className="text-white/70 hover:text-white transition-colors underline"
            >
              {isEnglish ? "Legal documents" : "Юридические документы"}
            </Link>
          </div>
          <div>VizuAI, 2026</div>
        </div>
      </div>
    </footer>
  );
}
