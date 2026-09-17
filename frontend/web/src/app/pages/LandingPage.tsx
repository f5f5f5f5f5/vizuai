import { Hero } from "@/app/components/Hero";
import { Features } from "@/app/components/Features";
import { Examples } from "@/app/components/Examples";
import { HowItWorks } from "@/app/components/HowItWorks";
import { Stats } from "@/app/components/Stats";
import { FAQ } from "@/app/components/FAQ";
import { Footer } from "@/app/components/Footer";
import { ScrollToTop } from "@/app/components/ScrollToTop";
import { AnimatedSection } from "@/app/components/AnimatedSection";
import { ArrowRight } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { Link, useLocation, useNavigate } from "react-router";
import { useLocale } from "@/app/i18n";
import { Logo } from "@/app/components/Logo";
import { trackPublicClick } from "@/app/lib/analytics/client";

export function LandingPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isEnglish, publicPath, publicPathForLocale, loginPath } = useLocale();
  const currentPublicPath = isEnglish
    ? location.pathname.slice(3) || "/"
    : location.pathname || "/";
  const currentSearchAndHash = `${location.search}${location.hash}`;
  const ruPath = `${publicPathForLocale(currentPublicPath, "ru")}${currentSearchAndHash}`;
  const enPath = `${publicPathForLocale(currentPublicPath, "en")}${currentSearchAndHash}`;

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="absolute top-0 left-0 right-0 z-50">
        <div className="flex items-start justify-between gap-4 px-4 pt-4 sm:px-6 sm:pt-6">
          <Logo height={48} />
          <div className="hidden items-center gap-2 rounded-full bg-white/10 px-3 py-2 text-sm text-white backdrop-blur-sm md:flex">
            <Link to={ruPath} className={!isEnglish ? "font-semibold" : "opacity-80"}>RU</Link>
            <span>/</span>
            <Link to={enPath} className={isEnglish ? "font-semibold" : "opacity-80"}>EN</Link>
          </div>
          <Button
            className="bg-white text-[#2C3419] hover:bg-white/90 shadow-lg self-start sm:self-auto"
            onClick={() => {
              void trackPublicClick("landing", "header_login_click");
              navigate(loginPath);
            }}
          >
            {isEnglish ? "Open the app" : "Войти в приложение"}
            <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <main>
        <Hero />
        <AnimatedSection>
          <Features />
        </AnimatedSection>
        <AnimatedSection>
          <Examples />
        </AnimatedSection>
        <AnimatedSection>
          <HowItWorks />
        </AnimatedSection>
        <AnimatedSection>
          <Stats />
        </AnimatedSection>
        <AnimatedSection>
          <FAQ />
        </AnimatedSection>
      </main>

      {/* Footer */}
      <Footer />
      
      {/* Scroll to Top Button */}
      <ScrollToTop />
    </div>
  );
}
