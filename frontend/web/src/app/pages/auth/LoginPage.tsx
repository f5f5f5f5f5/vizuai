import { useEffect, useMemo, useRef, useState } from "react";
import { Mail, ArrowRight, Check, Loader2 } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { useAuth } from "@/app/contexts/AuthContext";
import { LogoApp } from "@/app/components/LogoApp";
import { useLocale } from "@/app/i18n";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, ApiError } from "@/app/lib/api";
import { getVisitorContextIfConsented } from "@/app/lib/analytics/visitor";
import { trackPublicClick } from "@/app/lib/analytics/client";
import type { AppLocale } from "@/app/i18n";

function isMobileUserAgent(): boolean {
  if (typeof navigator === "undefined") {
    return false;
  }
  return /iPhone|iPad|iPod|Android/i.test(navigator.userAgent || "");
}

function normalizeLocaleParam(value: string | null): AppLocale | null {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized.startsWith("en")) {
    return "en";
  }
  if (normalized.startsWith("ru")) {
    return "ru";
  }
  return null;
}

export function LoginPage() {
  const RESEND_COOLDOWN_SECONDS = 30;
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [mobileVerificationConfirmed, setMobileVerificationConfirmed] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const { login, verify, isAuthenticated, user, refreshSession } = useAuth();
  const { locale, isEnglish, publicPath } = useLocale();
  const navigate = useNavigate();
  const token = useMemo(() => searchParams.get("token"), [searchParams]);
  const explicitLocale = useMemo(() => normalizeLocaleParam(searchParams.get("lang")), [searchParams]);
  const isMobileTokenFlow = useMemo(() => Boolean(token) && isMobileUserAgent(), [token]);
  const shouldVerifyToken = useMemo(
    () => Boolean(token) && (!isMobileTokenFlow || mobileVerificationConfirmed),
    [token, isMobileTokenFlow, mobileVerificationConfirmed],
  );
  const verificationAttemptTokenRef = useRef<string | null>(null);
  const verifyRef = useRef(verify);

  useEffect(() => {
    verifyRef.current = verify;
  }, [verify]);

  useEffect(() => {
    if (isAuthenticated && !token) {
      let cancelled = false;

      const syncLocaleAndOpenApp = async () => {
        if (explicitLocale && user?.locale !== explicitLocale) {
          try {
            await api.updateAccount({ locale: explicitLocale });
            await refreshSession();
          } catch (error) {
            console.debug("Account locale sync before app redirect failed:", error);
          }
        }
        if (!cancelled) {
          navigate("/app", { replace: true });
        }
      };

      void syncLocaleAndOpenApp();

      return () => {
        cancelled = true;
      };
    }
  }, [explicitLocale, isAuthenticated, navigate, refreshSession, token, user?.locale]);

  useEffect(() => {
    if (!emailSent || resendCooldown <= 0) {
      return;
    }
    const timer = window.setTimeout(() => {
      setResendCooldown((current) => Math.max(current - 1, 0));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [emailSent, resendCooldown]);

  const resolvePostLoginPath = async () => {
    try {
      const history = await api.getHistory(1, 1);
      if ((history.items || []).length === 0) {
        return "/app/workspace";
      }
    } catch (error) {
      console.debug("Post-login history check failed:", error);
    }
    return "/app";
  };

  useEffect(() => {
    if (!token || !shouldVerifyToken) {
      return;
    }
    if (verificationAttemptTokenRef.current === token) {
      return;
    }
    verificationAttemptTokenRef.current = token;

    let cancelled = false;

    const run = async () => {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const { anonId, acquisition } = getVisitorContextIfConsented();
        await verifyRef.current(token, {
          anon_id: anonId,
          acquisition,
          locale,
        });
        if (!cancelled) {
          const nextPath = await resolvePostLoginPath();
          if (!cancelled) {
            navigate(nextPath, { replace: true });
          }
        }
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError) {
            setErrorMessage(error.message);
          } else {
            setErrorMessage(isEnglish ? "Could not verify the sign-in link." : "Не удалось подтвердить ссылку для входа.");
          }
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [isEnglish, locale, navigate, shouldVerifyToken, token]);

  const sendMagicLink = async (nextEmail: string) => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      await login(nextEmail, locale);
      setEmailSent(true);
      setResendCooldown(RESEND_COOLDOWN_SECONDS);
      return true;
    } catch (error) {
      console.error("Login error:", error);
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage(isEnglish ? "Could not send the sign-in link." : "Не удалось отправить ссылку для входа.");
      }
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!email || !email.includes("@")) {
      return;
    }
    try {
      void trackPublicClick("login", "magic_link_start_submit", {
        email_domain: email.includes("@") ? email.split("@").pop() : null,
      });
      await sendMagicLink(email);
    } catch {}
  };

  return (
    <div className="min-h-screen bg-[#F5F3E7] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <LogoApp height={60} className="mx-auto" />
          <p className="text-gray-600 mt-4">{isEnglish ? "AI-powered interior design" : "Дизайн интерьера с искусственным интеллектом"}</p>
        </div>

        {/* Login Card */}
        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-lg sm:p-8">
          {token && isMobileTokenFlow && !mobileVerificationConfirmed && !isLoading ? (
            <div className="text-center">
              <div className="w-16 h-16 bg-[#7A8B4A]/10 rounded-full flex items-center justify-center mx-auto mb-4">
                <Mail className="w-8 h-8 text-[#7A8B4A]" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {isEnglish ? "Open the link in your main browser" : "Откройте ссылку в основном браузере"}
              </h2>
              <p className="text-sm text-gray-600 mb-6">
                {isEnglish
                  ? "If the email opened inside a mail app, switch to Safari or Chrome first. The sign-in link is single-use, so it is safer to confirm it in your main browser."
                  : "Если письмо открылось внутри почтового приложения, сначала перейдите в Safari или Chrome. Ссылка для входа одноразовая, поэтому лучше подтверждать её уже в основном браузере."}
              </p>
              <div className="bg-[#7A8B4A]/10 rounded-xl p-4 mb-6 text-sm text-gray-700">
                {isEnglish ? "Once you are in Safari or Chrome, press the button below." : "Когда окажетесь в Safari или Chrome, просто нажмите кнопку ниже."}
              </div>
              {errorMessage && (
                <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {errorMessage}
                </div>
              )}
              <Button
                type="button"
                onClick={() => {
                  void trackPublicClick("login", "mobile_magic_link_continue");
                  setMobileVerificationConfirmed(true);
                }}
                className="w-full bg-[#7A8B4A] hover:bg-[#6a7a3f] text-white h-12 text-base font-medium"
              >
                {isEnglish ? "Continue sign-in" : "Продолжить вход"}
                <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
            </div>
          ) : token && isLoading ? (
            <div className="text-center">
              <div className="w-16 h-16 bg-[#7A8B4A]/10 rounded-full flex items-center justify-center mx-auto mb-4">
                <Loader2 className="w-8 h-8 text-[#7A8B4A] animate-spin" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {isEnglish ? "Verifying sign-in" : "Подтверждаем вход"}
              </h2>
              <p className="text-gray-600">
                {isEnglish ? "We are checking the sign-in link and opening your account." : "Проверяем ссылку для входа и открываем ваш аккаунт."}
              </p>
            </div>
          ) : !emailSent ? (
            <>
              <div className="text-center mb-6">
                <div className="w-16 h-16 bg-[#7A8B4A]/10 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Mail className="w-8 h-8 text-[#7A8B4A]" />
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-2">
                  {isEnglish ? "Sign in" : "Вход в аккаунт"}
                </h2>
                <p className="text-sm text-gray-600">
                  {isEnglish ? "Passwordless sign-in by email link" : "Войдите без пароля — ссылка придет на email"}
                </p>
                <p className="text-sm text-gray-500 mt-2">
                  {isEnglish ? "After sign-in you can go straight to your first request" : "После входа вы сможете сразу перейти к созданию первого запроса"}
                </p>
              </div>

              {errorMessage && (
                <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {errorMessage}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                    {isEnglish ? "Email address" : "Email адрес"}
                  </label>
                  <input
                    type="email"
                    id="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@example.com"
                    required
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#7A8B4A] focus:border-transparent transition-all"
                  />
                </div>

                <Button
                  type="submit"
                  disabled={isLoading || !email.includes("@")}
                  className="w-full bg-[#7A8B4A] hover:bg-[#6a7a3f] text-white h-12 text-base font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                      {isEnglish ? "Sending..." : "Отправка..."}
                    </>
                  ) : (
                    <>
                      {isEnglish ? "Send sign-in link" : "Получить ссылку для входа"}
                      <ArrowRight className="w-5 h-5 ml-2" />
                    </>
                  )}
                </Button>
              </form>

              <div className="mt-6 pt-6 border-t border-gray-200">
                <p className="text-xs text-gray-500 text-center mb-3">
                  {isEnglish ? "By clicking \"Send link\", you agree to the " : "Нажимая \"Отправить ссылку\", вы соглашаетесь с "}
                  <Link to={publicPath("/legal")} className="text-[#7A8B4A] hover:underline">
                    {isEnglish ? "terms of use" : "условиями использования"}
                  </Link>{" "}
                  {isEnglish ? "and the " : "и "}
                  <Link to={publicPath("/legal")} className="text-[#7A8B4A] hover:underline">
                    {isEnglish ? "privacy policy" : "политикой конфиденциальности"}
                  </Link>
                </p>
              </div>
            </>
          ) : (
            <div className="text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <Check className="w-8 h-8 text-green-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {isEnglish ? "Check your inbox" : "Проверьте почту"}
              </h2>
              <p className="text-gray-600 mb-2">
                {isEnglish ? <>We sent a sign-in link to <strong>{email}</strong></> : <>Мы отправили ссылку для входа на <strong>{email}</strong></>}
              </p>
              <p className="text-sm text-gray-600 mb-6">
                {isEnglish ? "Open the email and follow the link to sign in to VizuAI" : "Откройте письмо и перейдите по ссылке, чтобы войти в VizuAI"}
              </p>

              {errorMessage && (
                <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {errorMessage}
                </div>
              )}

              <div className="bg-[#7A8B4A]/10 rounded-xl p-4 mb-6 text-left">
                <p className="text-sm text-gray-700">
                  {isEnglish ? "The email usually arrives within 1–2 minutes" : "Письмо обычно приходит в течение 1–2 минут"}
                </p>
                <p className="text-sm text-gray-700 mt-2">
                  {isEnglish ? "If it is not in inbox, check spam" : "Если его нет во входящих, проверьте папку \"Спам\""}
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
                <Button
                  type="button"
                  variant="outline"
                  disabled={isLoading || resendCooldown > 0}
                  onClick={() => {
                    void trackPublicClick("login", "magic_link_resend_click", {
                      email_domain: email.includes("@") ? email.split("@").pop() : null,
                    });
                    void sendMagicLink(email);
                  }}
                  className="border-gray-300 text-gray-700 hover:bg-gray-50"
                >
                  {isLoading
                    ? isEnglish
                      ? "Sending..."
                      : "Отправляем..."
                    : resendCooldown > 0
                      ? isEnglish
                        ? `Resend in ${resendCooldown}s`
                        : `Отправить повторно через ${resendCooldown} с`
                      : isEnglish
                        ? "Resend link"
                        : "Отправить ссылку повторно"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    void trackPublicClick("login", "magic_link_change_email");
                    setEmailSent(false);
                    setResendCooldown(0);
                    setErrorMessage(null);
                  }}
                  className="text-[#7A8B4A] hover:bg-[#7A8B4A]/10"
                >
                  {isEnglish ? "Change email" : "Изменить email"}
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Back to home */}
        <div className="text-center mt-6">
          <Link
            to={publicPath("/")}
            onClick={() => {
              void trackPublicClick("login", "back_to_landing");
            }}
            className="text-sm text-gray-600 hover:text-[#7A8B4A] transition-colors"
          >
            {isEnglish ? "← Back to home" : "← Вернуться на главную"}
          </Link>
        </div>
      </div>
    </div>
  );
}
