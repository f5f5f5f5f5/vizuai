import { Clock3, Headphones, SearchCheck, ShieldCheck, Sparkles, Workflow } from "lucide-react";

import { HowItWorks } from "@/app/components/HowItWorks";
import { PublicPageShell } from "@/app/components/PublicPageShell";
import { useLocale } from "@/app/i18n";

const explanationCards = [
  {
    icon: Workflow,
    title: "Понятный путь от загрузки до результата",
    description: "Вы загружаете фото, задаёте направление и получаете готовый результат в одном интерфейсе, без сложной настройки и лишних шагов.",
  },
  {
    icon: Clock3,
    title: "Быстро, но не в ущерб качеству",
    description: "Результат не появляется мгновенно, потому что VizuAI проходит через несколько этапов обработки и отбора, чтобы получить наиболее удачный вариант.",
  },
  {
    icon: ShieldCheck,
    title: "Честное отношение к качеству",
    description: "Мы открыто говорим о возможных артефактах AI и не прячемся, если результат получился слабым: в спорных случаях готовы помочь с повтором, промокодом или возвратом запросов.",
  },
];

export function HowItWorksPage() {
  const { isEnglish } = useLocale();
  const explanationCards = [
    {
      icon: Workflow,
      title: isEnglish ? "A clear path from upload to result" : "Понятный путь от загрузки до результата",
      description: isEnglish
        ? "You upload a photo, set the direction, and get a finished result inside one interface without heavy setup."
        : "Вы загружаете фото, задаёте направление и получаете готовый результат в одном интерфейсе, без сложной настройки и лишних шагов.",
    },
    {
      icon: Clock3,
      title: isEnglish ? "Fast without pretending quality is instant" : "Быстро, но не в ущерб качеству",
      description: isEnglish
        ? "The result is not instant because VizuAI goes through several processing and selection steps to pick a stronger outcome."
        : "Результат не появляется мгновенно, потому что VizuAI проходит через несколько этапов обработки и отбора, чтобы получить наиболее удачный вариант.",
    },
    {
      icon: ShieldCheck,
      title: isEnglish ? "Honest quality expectations" : "Честное отношение к качеству",
      description: isEnglish
        ? "We talk openly about possible AI artifacts and do not hide when a result is weak. In disputed cases we can review reruns, promo codes, or request refunds."
        : "Мы открыто говорим о возможных артефактах AI и не прячемся, если результат получился слабым: в спорных случаях готовы помочь с повтором, промокодом или возвратом запросов.",
    },
  ];

  return (
    <PublicPageShell
      eyebrow={isEnglish ? "How it works" : "Как это работает"}
      title={isEnglish ? "How VizuAI works" : "Как работает VizuAI"}
      description={
        isEnglish
          ? "A plain-language overview of how VizuAI creates new interiors and searches furniture by photo. No unnecessary jargon, but honest about the process and result."
          : "Объясняем простыми словами, как VizuAI создаёт новые варианты интерьера и как проходит поиск мебели по фото. Без лишней технички, но честно о процессе и результате."
      }
    >
      <section className="bg-[#F5F3E7] px-6 py-16">
        <div className="mx-auto grid max-w-6xl gap-6 md:grid-cols-3">
          {explanationCards.map((item) => (
            <div key={item.title} className="rounded-2xl border border-[#E7E2CC] bg-white p-6 shadow-sm">
              <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[#7A8B4A]/10 text-[#7A8B4A]">
                <item.icon className="h-6 w-6" />
              </div>
              <h2 className="mb-2 text-xl text-[#2C3419]">{item.title}</h2>
              <p className="text-sm leading-7 text-[#5A6B3A]">{item.description}</p>
            </div>
          ))}
        </div>
      </section>

      <HowItWorks showHeading={false} showCta={false} sectionClassName="bg-white px-6 py-12 sm:py-16" />

      <section className="bg-[#F5F3E7] px-6 py-16">
        <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-2">
          <div className="rounded-3xl border border-[#E7E2CC] bg-white p-8 shadow-sm">
            <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[#7A8B4A]/10 text-[#7A8B4A]">
              <Sparkles className="h-6 w-6" />
            </div>
            <h2 className="mb-4 text-3xl text-[#2C3419]">{isEnglish ? "How the interior render is created" : "Как создаётся интерьерный рендер"}</h2>
            <div className="space-y-4 text-base leading-8 text-[#5A6B3A]">
              <p>
                {isEnglish ? "We aim to get the strongest possible visual result based on your photo, text request, and reference image when needed." : "Мы стараемся получить максимально сильный визуальный результат на основе вашего фото, текстового запроса и, при необходимости, референса."}
              </p>
              <p>
                {isEnglish ? "To do that, VizuAI does not rely on one attempt only. The system tries several variants and selects the stronger one so the final image looks coherent and convincing." : "Для этого VizuAI не ограничивается одной попыткой: сервис делает несколько вариантов и выбирает наиболее удачный, чтобы итог выглядел цельно, аккуратно и убедительно."}
              </p>
              <p>
                {isEnglish ? "The goal is not just to generate a picture, but to give you a visualization you can actually use when deciding on renovation direction, furniture, and style." : "Наша цель не просто “сгенерировать картинку”, а дать визуализацию, на которую действительно можно опереться при выборе направления ремонта, мебели и стиля."}
              </p>
            </div>
          </div>

          <div className="rounded-3xl border border-[#E7E2CC] bg-white p-8 shadow-sm">
            <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[#7A8B4A]/10 text-[#7A8B4A]">
              <SearchCheck className="h-6 w-6" />
            </div>
            <h2 className="mb-4 text-3xl text-[#2C3419]">{isEnglish ? "How furniture search works" : "Как проходит поиск мебели"}</h2>
            <div className="space-y-4 text-base leading-8 text-[#5A6B3A]">
              <p>
                {isEnglish ? "The service first identifies objects in the image and then keeps the ones that belong to furniture and decor." : "Сначала сервис определяет объекты на изображении, затем отбирает те, которые относятся к мебели и предметам интерьера."}
              </p>
              <p>
                {isEnglish ? "After that, each object gets its own search flow. VizuAI gathers similar marketplace options and groups them so comparison is meaningful instead of mixed in one feed." : "После этого по каждому объекту начинается отдельный поиск: VizuAI собирает похожие варианты на маркетплейсах и группирует их так, чтобы было удобно сравнивать предложения по смыслу, а не в одной общей ленте."}
              </p>
              <p>
                {isEnglish ? "It is not always an exact match down to the last detail, but it is a practical way to move from an inspiring image to real products quickly." : "Это не всегда точное совпадение до последней детали, но хороший способ быстро перейти от понравившегося кадра к реальным товарам."}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white px-6 py-16">
        <div className="mx-auto grid max-w-6xl gap-6 md:grid-cols-2">
          <div className="rounded-3xl border border-[#E7E2CC] bg-[#F5F3E7] p-8">
            <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-[#7A8B4A] shadow-sm">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <h2 className="mb-4 text-3xl text-[#2C3419]">{isEnglish ? "Honest note about limitations" : "Честно о возможных недочётах"}</h2>
            <p className="text-base leading-8 text-[#5A6B3A]">
              {isEnglish ? "VizuAI is an AI service, so artifacts or inaccuracies in geometry, materials, furniture details, or secondary objects can happen. We do not treat that as ideal, but we also do not pretend such cases are impossible." : "VizuAI — это AI-сервис, поэтому в отдельных случаях возможны артефакты, неточности в геометрии, материалах, деталях мебели или второстепенных объектах. Мы не считаем это нормой, но и не делаем вид, что такие случаи невозможны."}
            </p>
          </div>

          <div className="rounded-3xl border border-[#E7E2CC] bg-[#F5F3E7] p-8">
            <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-[#7A8B4A] shadow-sm">
              <Headphones className="h-6 w-6" />
            </div>
            <h2 className="mb-4 text-3xl text-[#2C3419]">{isEnglish ? "If the result was not good enough" : "Если результат не устроил"}</h2>
            <p className="text-base leading-8 text-[#5A6B3A]">
              {isEnglish ? "Write to us in Telegram or at owner@vizuai.example. If the result is genuinely weak, we can discuss a rerun, promo code, or refund of the spent requests. For us that is part of the service, not something we avoid talking about." : "Напишите нам в Telegram или на owner@vizuai.example. Если работа действительно получилась слабой, мы готовы обсудить повторный запуск, промокод или возврат потраченных запросов. Для нас это нормальная часть сервиса, а не исключение, о котором неудобно говорить."}
            </p>
          </div>
        </div>
      </section>
    </PublicPageShell>
  );
}
