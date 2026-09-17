import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { Link, useLocation } from "react-router";

import { Footer } from "@/app/components/Footer";
import { LogoApp } from "@/app/components/LogoApp";
import { useLocale } from "@/app/i18n";
import { Button } from "@/app/components/ui/button";
import { trackPublicClick } from "@/app/lib/analytics/client";

type PublicPageShellProps = {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
};

export function PublicPageShell({ eyebrow, title, description, children }: PublicPageShellProps) {
  const location = useLocation();
  const { isEnglish, publicPath, publicPathForLocale, loginPath } = useLocale();
  const currentPublicPath = isEnglish
    ? location.pathname.slice(3) || "/"
    : location.pathname || "/";
  const currentSearchAndHash = `${location.search}${location.hash}`;
  const ruPath = `${publicPathForLocale(currentPublicPath, "ru")}${currentSearchAndHash}`;
  const enPath = `${publicPathForLocale(currentPublicPath, "en")}${currentSearchAndHash}`;

  return (
    <div className="min-h-screen bg-[#F5F3E7]">
      <header className="border-b border-[#E7E2CC] bg-[#F5F3E7]/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center justify-between gap-4">
            <Link
              to={publicPath("/")}
              onClick={() => {
                void trackPublicClick("public_page", "header_logo_click");
              }}
              className="inline-flex items-center"
            >
              <LogoApp height={40} />
            </Link>
            <div className="hidden items-center gap-2 text-sm text-[#5A6B3A] lg:flex">
              <Link to={ruPath} className={!isEnglish ? "font-semibold text-[#2C3419]" : "hover:text-[#2C3419]"}>
                RU
              </Link>
              <span>/</span>
              <Link to={enPath} className={isEnglish ? "font-semibold text-[#2C3419]" : "hover:text-[#2C3419]"}>
                EN
              </Link>
            </div>
            <Button
              asChild
              className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F] lg:hidden"
            >
              <Link
                to={loginPath}
                onClick={() => {
                  void trackPublicClick("public_page", "header_login_click");
                }}
              >
                {isEnglish ? "Open the app" : "Открыть приложение"}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
          <Button
            asChild
            className="hidden bg-[#7A8B4A] text-white hover:bg-[#6B7B3F] lg:inline-flex"
          >
            <Link
              to={loginPath}
              onClick={() => {
                void trackPublicClick("public_page", "header_login_click");
              }}
            >
              {isEnglish ? "Open the app" : "Открыть приложение"}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </header>

      <main>
        <section className="border-b border-[#E7E2CC] bg-white">
          <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
            <p className="mb-4 text-sm font-semibold uppercase tracking-[0.18em] text-[#7A8B4A]">
              {eyebrow}
            </p>
            <h1 className="max-w-4xl text-4xl leading-tight text-[#2C3419] sm:text-5xl">
              {title}
            </h1>
            <p className="mt-5 max-w-3xl text-lg leading-8 text-[#5A6B3A] sm:text-xl">
              {description}
            </p>
          </div>
        </section>

        {children}
      </main>

      <Footer />
    </div>
  );
}
