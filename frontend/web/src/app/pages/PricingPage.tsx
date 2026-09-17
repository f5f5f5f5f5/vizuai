import { CheckCircle2, CreditCard, Gift, Sparkles, Sofa } from "lucide-react";
import { Link } from "react-router";

import { PublicPageShell } from "@/app/components/PublicPageShell";
import { Button } from "@/app/components/ui/button";
import { useLocale } from "@/app/i18n";
import { trackPublicClick } from "@/app/lib/analytics/client";

const plans = [
  {
    credits: 1,
    amount: "199 ₽",
    perRequest: "199 ₽ за запрос",
    label: "Быстрый старт",
  },
  {
    credits: 3,
    amount: "549 ₽",
    perRequest: "183 ₽ за запрос",
    label: "Оптимальный пакет",
  },
  {
    credits: 10,
    amount: "1599 ₽",
    perRequest: "160 ₽ за запрос",
    label: "Самый выгодный",
  },
];

const pricingNotes = [
  "1 запрос расходуется на любой основной сценарий: дизайн интерьера, дизайн по референсу или поиск мебели.",
  "Баланс хранится в аккаунте и подходит для всех сценариев внутри VizuAI.",
  "Если результат получился слабым по качеству, мы готовы рассмотреть повторный запуск, промокод или возврат потраченных запросов.",
];

const useCases = [
  {
    icon: Sparkles,
    title: "Дизайн интерьера по фото",
    description: "Загрузите фото комнаты и опишите желаемый результат.",
  },
  {
    icon: CreditCard,
    title: "Дизайн по референсу",
    description: "Используйте изображение-образец, чтобы перенести настроение и стиль на своё помещение.",
  },
  {
    icon: Sofa,
    title: "Подбор мебели по фото",
    description: "Получите подборку похожих товаров по объектам на изображении.",
  },
];

export function PricingPage() {
  const { isEnglish, loginPath } = useLocale();
  const plansLocalized = plans.map((plan) => ({
    ...plan,
    label:
      plan.credits === 1
        ? isEnglish
          ? "Trial"
          : plan.label
        : plan.credits === 3
          ? isEnglish
            ? "Balanced pack"
            : plan.label
          : isEnglish
            ? "Best value"
            : plan.label,
    perRequest: isEnglish
      ? `${plan.credits === 1 ? "199 RUB" : plan.credits === 3 ? "183 RUB" : "160 RUB"} per request`
      : plan.perRequest,
  }));
  const pricingNotesLocalized = isEnglish
    ? [
        "1 request is used for any main scenario: interior design, design by reference, or furniture search.",
        "Your balance is stored in the account and works across all scenarios inside VizuAI.",
        "If a result is genuinely weak, we can review a rerun, promo code, or a refund of the spent requests.",
      ]
    : pricingNotes;
  const useCasesLocalized = useCases.map((item) => ({
    ...item,
    title:
      item.title === "Дизайн интерьера по фото"
        ? isEnglish
          ? "Interior design from photo"
          : item.title
        : item.title === "Дизайн по референсу"
          ? isEnglish
            ? "Design by reference"
            : item.title
          : isEnglish
            ? "Furniture search by photo"
            : item.title,
    description:
      item.title === "Дизайн интерьера по фото"
        ? isEnglish
          ? "Upload a room photo and describe the result you want"
          : item.description
        : item.title === "Дизайн по референсу"
          ? isEnglish
            ? "Use an inspiration image to transfer mood and style to your room"
            : item.description
          : isEnglish
            ? "Get grouped links to similar products for objects in the image"
            : item.description,
  }));

  return (
    <PublicPageShell
      eyebrow={isEnglish ? "Pricing and payments" : "Цены и оплата"}
      title={isEnglish ? "VizuAI pricing and how requests work" : "Стоимость VizuAI и как устроены запросы"}
      description={
        isEnglish
          ? "A transparent pay-per-use model with no subscription: add requests to your balance and use them across all core VizuAI scenarios."
          : "Прозрачная система оплаты без подписки: вы пополняете баланс запросов и используете его для любых основных сценариев внутри VizuAI."
      }
    >
      <section className="bg-[#F5F3E7] px-6 py-16">
        <div className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-3xl border border-[#E7E2CC] bg-white p-8 shadow-sm">
            <p className="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-[#7A8B4A]">{isEnglish ? "Core principle" : "Базовый принцип"}</p>
            <h2 className="mb-4 text-4xl text-[#2C3419]">{isEnglish ? "One request = one scenario run" : "Один запрос = один запуск сценария"}</h2>
            <p className="mb-6 text-lg leading-8 text-[#5A6B3A]">
              {isEnglish
                ? "The same balance works for interior redesign, reference-based design, and furniture search. You do not pay for access, subscription, or separate features. You only pay for actual runs."
                : "Один и тот же баланс работает для интерьерного дизайна, сценария по референсу и подбора мебели по фото. Вы не платите за доступ, подписку или отдельные функции: оплачиваются только сами запуски."}
            </p>
            <div className="space-y-3">
              {pricingNotesLocalized.map((note) => (
                <div key={note} className="flex items-start gap-3 rounded-2xl bg-[#F5F3E7] p-4">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-[#7A8B4A]" />
                  <p className="text-sm leading-7 text-[#5A6B3A]">{note}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl bg-[#5A6B3A] p-8 text-white shadow-sm">
            <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-white">
              <Gift className="h-6 w-6" />
            </div>
            <p className="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-white/70">{isEnglish ? "Bonus" : "Для внимательных"}</p>
            <h2 className="mb-4 text-3xl">Промокод YNEW15</h2>
            <p className="mb-4 text-base leading-8 text-white/80">
              {isEnglish
                ? "If the promo code is active at the time of purchase, it gives 15% off. It is a small bonus for people who actually study the product before buying."
                : "Если промокод активен на момент покупки, он даст скидку 15% на заказ. Это маленький бонус для тех, кто дошёл до этой страницы и действительно изучает сервис внимательно."}
            </p>
            <p className="mb-8 text-sm leading-7 text-white/70">
              {isEnglish ? "Promo codes and discounts are applied during checkout inside the app" : "Промокоды и скидки применяются уже на этапе оплаты внутри приложения."}
            </p>
            <Button
              asChild
              className="w-full bg-white text-[#2C3419] hover:bg-white/90"
            >
              <Link
                to={loginPath}
                onClick={() => {
                  void trackPublicClick("pricing", "open_app_click");
                }}
              >
                {isEnglish ? "See packs in the app" : "Посмотреть пакеты в приложении"}
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-8 text-3xl text-[#2C3419] sm:text-4xl">{isEnglish ? "Request packs" : "Пакеты запросов"}</h2>
          <div className="grid gap-6 md:grid-cols-3">
            {plansLocalized.map((plan) => (
              <div key={plan.credits} className="rounded-3xl border border-[#E7E2CC] bg-[#F5F3E7] p-8">
                <p className="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-[#7A8B4A]">{plan.label}</p>
                <div className="mb-4 flex items-end gap-3">
                  <span className="text-5xl text-[#2C3419]">{plan.credits}</span>
                  <span className="pb-1 text-lg text-[#5A6B3A]">{isEnglish ? (plan.credits === 1 ? "request" : "requests") : plan.credits === 1 ? "запрос" : "запросов"}</span>
                </div>
                <p className="text-3xl text-[#2C3419]">{plan.amount}</p>
                <p className="mt-3 text-sm leading-7 text-[#5A6B3A]">{plan.perRequest}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-8 text-3xl text-[#2C3419] sm:text-4xl">{isEnglish ? "What you can run with one balance" : "Что можно запустить на одном балансе"}</h2>
          <div className="grid gap-6 md:grid-cols-3">
            {useCasesLocalized.map((item) => (
              <div key={item.title} className="rounded-2xl border border-[#E7E2CC] bg-[#F5F3E7] p-6">
                <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-[#7A8B4A] shadow-sm">
                  <item.icon className="h-6 w-6" />
                </div>
                <h3 className="mb-2 text-xl text-[#2C3419]">{item.title}</h3>
                <p className="text-sm leading-7 text-[#5A6B3A]">{item.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </PublicPageShell>
  );
}
