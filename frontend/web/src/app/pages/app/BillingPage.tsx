import { AlertCircle, Check, Landmark, RotateCw, Zap } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTheme } from "@/app/contexts/ThemeContext";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useAuth } from "@/app/contexts/AuthContext";
import { useLocale } from "@/app/i18n";
import { api, ApiError, type BillingPlan, type BillingPromocodePreview } from "@/app/lib/api";
import { loadBillingResume } from "@/app/lib/billingResume";
import { requestWord } from "@/app/lib/requestLabel";
import { trackAppClick } from "@/app/lib/analytics/client";
import { reachYandexGoalOnce } from "@/app/lib/analytics/yandexMetrica";

export function BillingPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [selectedPackage, setSelectedPackage] = useState<number | null>(null);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCheckoutLoading, setIsCheckoutLoading] = useState(false);
  const [promocode, setPromocode] = useState("");
  const [appliedPromocode, setAppliedPromocode] = useState<BillingPromocodePreview | null>(null);
  const [isPromocodeLoading, setIsPromocodeLoading] = useState(false);
  const [promocodeError, setPromocodeError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const { isDarkMode } = useTheme();
  const { isEnglish, locale, publicPath } = useLocale();
  const { refreshSession } = useAuth();

  const loadBillingPlans = useCallback(async () => {
    setIsLoading(true);
    setBanner(null);
    try {
      const billingPlans = await api.getBillingPlans();
      setPlans(billingPlans);
      setSelectedPackage((current) => {
        if (!billingPlans.length) {
          return null;
        }
        return current ?? 1;
      });
    } catch (error) {
      console.error("Failed to load billing data:", error);
      setPlans([]);
      setSelectedPackage(null);
      setBanner(isEnglish ? "Could not load request packs." : "Не удалось загрузить пакеты запросов.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const packages = useMemo(
    () =>
      plans.map((plan, index) => ({
        id: index + 1,
        name: index === 0 ? (isEnglish ? "Trial" : "Пробный") : index === 1 ? (isEnglish ? "Balanced" : "Оптимальный") : isEnglish ? "Maximum" : "Максимум",
        amount: plan.credits,
        price: Number(plan.amount),
        badge: index === 0 ? (isEnglish ? "Try it" : "Попробовать") : index === 1 ? (isEnglish ? "Popular" : "Оптимально") : isEnglish ? "Best value" : "Выгодно",
        description:
          index === 0
            ? isEnglish ? "For your first run" : "Для первого запуска"
            : index === 1
              ? isEnglish ? "To compare several options" : "Чтобы сравнить несколько вариантов"
              : isEnglish ? "If you want extra balance" : "Если планируете работать с запасом",
        bonus: 0,
        popular: index === 1,
        provider: plan.provider,
      })),
    [isEnglish, plans],
  );

  useEffect(() => {
    void loadBillingPlans();
  }, [loadBillingPlans]);

  useEffect(() => {
    const checkoutId = searchParams.get("checkout");
    const returnStatus = searchParams.get("return");
    if (!checkoutId) {
      if (returnStatus === "success" && loadBillingResume()) {
        void refreshSession();
        navigate("/app/workspace", { replace: true, state: { billingReturn: "success" } });
      }
      return;
    }

    let cancelled = false;
    let timer: number | undefined;
    let attempts = 0;

    const loadCheckout = async () => {
      try {
        const checkout = await api.getCheckout(checkoutId);
        if (cancelled) return;

        if (checkout.status === "paid") {
          reachYandexGoalOnce("purchase", checkoutId);
          setBanner(isEnglish ? "Payment succeeded. Your balance is already updated." : "Оплата прошла успешно. Баланс уже обновлен.");
          await refreshSession();
          if (loadBillingResume()) {
            navigate("/app/workspace", { replace: true, state: { billingReturn: "success" } });
          }
          return;
        }

        if (checkout.status === "canceled" || checkout.status === "refunded") {
          setBanner(isEnglish ? "Payment was not completed." : "Оплата не была завершена.");
          return;
        }

        attempts += 1;
        setBanner(isEnglish ? "Checking payment status. If payment already succeeded, the balance will update automatically." : "Проверяем статус оплаты. Если оплата уже прошла, баланс обновится автоматически.");
        if (attempts < 10) {
          timer = window.setTimeout(() => {
            void loadCheckout();
          }, 3000);
        }
      } catch (error) {
        console.error("Failed to load checkout:", error);
      }
    };

    void loadCheckout();

    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [navigate, searchParams, refreshSession]);

  const selectedPlan = packages.find((pkg) => pkg.id === selectedPackage) || null;

  useEffect(() => {
    setAppliedPromocode(null);
    setPromocodeError(null);
  }, [selectedPackage]);

  const handleApplyPromocode = async () => {
    if (!selectedPlan || !promocode.trim() || isPromocodeLoading) {
      return;
    }

    setIsPromocodeLoading(true);
    setPromocodeError(null);
    void trackAppClick("billing", "promocode_apply_click", {
      provider: selectedPlan.provider,
      credits: selectedPlan.amount,
    });
    try {
      const preview = await api.checkBillingPromocode(selectedPlan.amount, promocode.trim(), selectedPlan.provider);
      setAppliedPromocode(preview);
      setPromocode(preview.code);
    } catch (error) {
      setAppliedPromocode(null);
      if (error instanceof ApiError) {
        setPromocodeError(error.message);
      } else {
        setPromocodeError(isEnglish ? "Could not validate the promo code." : "Не удалось проверить промокод.");
      }
    } finally {
      setIsPromocodeLoading(false);
    }
  };

  const handleClearPromocode = () => {
    setPromocode("");
    setAppliedPromocode(null);
    setPromocodeError(null);
  };

  const handleCheckout = async () => {
    if (!selectedPlan || isCheckoutLoading) {
      return;
    }

    setIsCheckoutLoading(true);
    setBanner(null);
    void trackAppClick("billing", "checkout_click", {
      provider: selectedPlan.provider,
      credits: selectedPlan.amount,
      has_promocode: Boolean(appliedPromocode?.code),
    });
    try {
      const checkout = await api.createCheckout(
        selectedPlan.amount,
        selectedPlan.provider,
        appliedPromocode?.code ?? null,
      );
      if (checkout.checkout_url) {
        window.location.assign(checkout.checkout_url);
        return;
      }
      setBanner(isEnglish ? "Could not get the checkout link." : "Не удалось получить ссылку на оплату.");
    } catch (error) {
      console.error("Checkout failed:", error);
      if (error instanceof ApiError) {
        setBanner(error.message);
      } else {
        setBanner(isEnglish ? "Could not create checkout." : "Не удалось создать оплату.");
      }
    } finally {
      setIsCheckoutLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:space-y-8 sm:p-6 lg:p-8">
      {banner && (
        <div className={`rounded-xl px-4 py-3 text-sm ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800 text-gray-300" : "bg-white border border-gray-200 text-gray-700"}`}>
          {banner}
        </div>
      )}

      {/* Packages */}
      <div>
        <div className="mb-6">
          <h2 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Choose a pack" : "Выберите пакет"}</h2>
          <p className={`mt-2 text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>
            {isEnglish ? "One request is used for any core scenario" : "Один запрос расходуется на запуск любого сценария из предложенных"}
          </p>
        </div>
        {!isLoading && packages.length === 0 ? (
          <div className={`rounded-2xl p-6 text-center sm:p-10 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
            <div className={`mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full ${isDarkMode ? "bg-gray-800" : "bg-gray-100"}`}>
              <AlertCircle className={`h-8 w-8 ${isDarkMode ? "text-gray-500" : "text-gray-500"}`} />
            </div>
            <h3 className={`mb-2 text-lg font-semibold ${isDarkMode ? "text-white" : "text-gray-900"}`}>
              {isEnglish ? "Packs are temporarily unavailable" : "Пакеты временно недоступны"}
            </h3>
            <p className={`mx-auto mb-6 max-w-xl text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
              {isEnglish ? "Could not load top-up options. Try refreshing once more. If it keeps happening, contact support." : "Не получилось загрузить варианты пополнения. Попробуйте обновить данные ещё раз. Если проблема повторится, напишите в поддержку."}
            </p>
            <div className="flex flex-col justify-center gap-3 sm:flex-row">
              <Button
                type="button"
                onClick={() => void loadBillingPlans()}
                className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
              >
                <RotateCw className="mr-2 h-4 w-4" />
                {isEnglish ? "Try again" : "Попробовать снова"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate("/app/workspace")}
                className={isDarkMode ? "border-gray-700 bg-gray-900 text-gray-200 hover:bg-gray-800 hover:text-white" : "border-gray-300 text-gray-700 hover:bg-gray-50"}
              >
                {isEnglish ? "Back to studio" : "Вернуться в студию"}
              </Button>
            </div>
          </div>
        ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {(isLoading ? Array.from({ length: 3 }) : packages).map((pkg, index) => (
            isLoading ? (
              <div
                key={`skeleton-${index}`}
                className={`rounded-2xl p-5 animate-pulse sm:p-8 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}
              >
                <div className={`w-24 h-6 rounded-full mb-5 ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
                <div className={`w-40 h-7 rounded mb-3 ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
                <div className={`w-56 h-4 rounded mb-6 ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
                <div className={`w-28 h-10 rounded mb-3 ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
                <div className={`w-24 h-8 rounded ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
              </div>
            ) : (
            <button
              key={pkg.id}
              onClick={() => setSelectedPackage(pkg.id)}
              className={`relative border-2 rounded-2xl p-5 text-left transition-all duration-300 hover:scale-[1.02] sm:p-8 ${
                selectedPackage === pkg.id
                  ? 'border-[#7A8B4A] shadow-lg shadow-[#7A8B4A]/20'
                  : isDarkMode 
                    ? 'border-gray-800 hover:border-gray-700 bg-[#0F0F0F]' 
                    : 'border-gray-200 hover:border-gray-300 bg-white'
              }`}
            >
              {pkg.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="bg-[#C69C6D] text-white text-xs font-semibold px-4 py-1 rounded-full flex items-center gap-1">
                    <Zap className="w-3 h-3" />
                    {isEnglish ? "Popular" : "Популярный"}
                  </span>
                </div>
              )}

              <div className="mb-6">
                <div className={`inline-block px-3 py-1 rounded-full text-xs font-semibold mb-3 ${isDarkMode ? 'bg-[#7A8B4A]/20 text-[#7A8B4A]' : 'bg-[#7A8B4A]/10 text-[#7A8B4A]'}`}>
                  {pkg.badge}
                </div>
                <h3 className={`text-lg font-semibold mb-1 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{pkg.name}</h3>
                <p className={`text-sm mb-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{pkg.description}</p>
                <div className="flex items-baseline gap-2 mb-3">
                  <span className={`text-3xl font-bold sm:text-4xl ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{pkg.price}</span>
                  <span className={isDarkMode ? 'text-gray-400' : 'text-gray-600'}>₽</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className={`text-2xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{pkg.amount}</span>
                  <span className={isDarkMode ? 'text-gray-400' : 'text-gray-600'}>{requestWord(pkg.amount, locale)}</span>
                </div>
              </div>

              <div className="space-y-2 mb-6">
                <div className={`flex items-center gap-2 text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  <Check className="w-4 h-4 text-[#7A8B4A]" />
                  <span>{isEnglish ? "No expiration" : "Без ограничений по времени"}</span>
                </div>
                <div className={`flex items-center gap-2 text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  <Check className="w-4 h-4 text-[#7A8B4A]" />
                  <span>{isEnglish ? "Works for design and furniture search" : "Подходит для дизайна и поиска мебели"}</span>
                </div>
              </div>

              {selectedPackage === pkg.id && (
                <div className="absolute top-4 right-4">
                  <div className="bg-[#7A8B4A] rounded-full p-1">
                    <Check className="w-4 h-4 text-white" />
                  </div>
                </div>
              )}
            </button>
            )
          ))}
        </div>
        )}
      </div>

      {selectedPlan && !isLoading && (
          <div className={`rounded-xl p-5 space-y-4 sm:p-6 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
            <div>
              <h2 className={`text-xl font-semibold mb-1 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Promo code" : "Промокод"}</h2>
              <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "If you have a discount code, apply it before payment." : "Если у вас есть код на скидку, примените его перед оплатой."}</p>
            </div>
            {appliedPromocode && (
              <button
                type="button"
                onClick={handleClearPromocode}
                className={`text-sm ${isDarkMode ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-900'}`}
              >
                {isEnglish ? "Clear" : "Очистить"}
              </button>
            )}
          </div>

          <div className="flex flex-col md:flex-row gap-3">
            <input
              value={promocode}
              onChange={(event) => {
                setPromocode(event.target.value);
                setAppliedPromocode(null);
                setPromocodeError(null);
              }}
              placeholder={isEnglish ? "Enter promo code" : "Введите промокод"}
              className={`flex-1 rounded-xl px-4 py-3 outline-none transition-colors ${
                isDarkMode
                  ? 'bg-[#111111] border border-gray-800 text-white placeholder:text-gray-500 focus:border-[#7A8B4A]'
                  : 'bg-white border border-gray-200 text-gray-900 placeholder:text-gray-400 focus:border-[#7A8B4A]'
              }`}
            />
            <Button
              type="button"
              disabled={!promocode.trim() || isPromocodeLoading}
              onClick={handleApplyPromocode}
              className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F] disabled:opacity-60"
            >
              {isPromocodeLoading ? (isEnglish ? "Checking..." : "Проверяем...") : isEnglish ? "Apply" : "Применить"}
            </Button>
          </div>

          {promocodeError && (
            <div className={`text-sm ${isDarkMode ? 'text-[#F0B4B4]' : 'text-[#B44B4B]'}`}>{promocodeError}</div>
          )}

          {appliedPromocode && (
            <div className={`rounded-xl p-4 ${isDarkMode ? 'bg-[#111111] border border-gray-800' : 'bg-[#F8F8F5] border border-gray-200'}`}>
              <div className="flex items-center justify-between gap-4 mb-3">
                <div>
                  <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Promo code applied" : "Промокод применён"}</p>
                  <p className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{appliedPromocode.code}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-[#7A8B4A]">{isEnglish ? "Discount" : "Скидка"}</p>
                  <p className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>−{appliedPromocode.discount_amount} ₽</p>
                </div>
              </div>
              <div className={`flex items-center justify-between text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                <span>{isEnglish ? "Total" : "Итого к оплате"}</span>
                <span className={`text-base font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{appliedPromocode.amount_final} ₽</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Payment */}
      {selectedPlan && !isLoading && (
        <div className="space-y-6">
          <h2 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Payment" : "Оплата"}</h2>
          <div className={`rounded-xl p-5 flex items-start gap-4 sm:p-6 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
            <div className="rounded-2xl bg-[#7A8B4A]/10 p-4 text-[#7A8B4A]">
              <Landmark className="w-7 h-7" />
            </div>
            <div className="space-y-2">
              <p className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Checkout with T-Bank" : "Оплата через T-Bank"}</p>
              <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                {isEnglish ? "After redirect you can choose a bank card or SBP." : "После перехода вы сможете выбрать удобный способ оплаты: банковская карта или СБП."}
              </p>
            </div>
          </div>

          <Button
            size="lg"
            disabled={isCheckoutLoading}
            onClick={handleCheckout}
            className="w-full bg-[#7A8B4A] text-white hover:bg-[#6B7B3F] text-lg py-6 disabled:opacity-60"
          >
            {isCheckoutLoading
              ? isEnglish
                ? "Redirecting to checkout..."
                : "Переходим к оплате..."
              : `${isEnglish ? "Pay" : "Оплатить"} ${appliedPromocode?.amount_final ?? selectedPlan.price} ₽`}
          </Button>
          <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
            {isEnglish ? "Requests are added to your balance right after payment" : "Запросы зачислятся на баланс сразу после оплаты"}
          </p>
        </div>
      )}

      {/* Info */}
      <div className={`rounded-xl p-6 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
        <h4 className={`mb-3 font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>ℹ️ {isEnglish ? "Information" : "Информация"}</h4>
        <ul className={`space-y-2 text-sm mb-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
          <li>• {isEnglish ? "Requests are credited within seconds after payment" : "Запросы зачисляются через несколько секунд после оплаты"}</li>
          <li>• {isEnglish ? "Paid requests do not expire" : "Оплаченные запросы не сгорают"}</li>
          <li>• {isEnglish ? "1 request is spent per run" : "1 запрос списывается за 1 запуск"}</li>
          <li>• {isEnglish ? "If a request is already prepared, you can continue right after payment" : "Если запрос уже подготовлен, после оплаты можно сразу продолжить"}</li>
        </ul>
        <Link 
          to={publicPath("/legal")}
          className={`text-sm text-[#7A8B4A] hover:underline inline-flex items-center gap-1`}
        >
          📄 {isEnglish ? "Open legal documents" : "Ознакомиться с юридическими документами"}
        </Link>
      </div>
    </div>
  );
}
