import type { LucideIcon } from "lucide-react";
import { ArrowRight, CheckCircle2, ImageIcon, Palette, Search, Sofa, Sparkles, Upload, WandSparkles } from "lucide-react";
import { Link } from "react-router";

import { PublicPageShell } from "@/app/components/PublicPageShell";
import { Button } from "@/app/components/ui/button";
import { useLocale } from "@/app/i18n";
import { trackPublicClick } from "@/app/lib/analytics/client";

type UseCaseConfig = {
  routeKey: "interior" | "reference" | "furniture";
  eyebrow: string;
  title: string;
  description: string;
  icon: LucideIcon;
  points: string[];
  steps: Array<{ title: string; description: string; icon: LucideIcon }>;
  resultTitle: string;
  resultDescription: string;
  inputChecklist: string[];
  advice: string[];
  outputChecklist: string[];
};

function UseCasePage({ config }: { config: UseCaseConfig }) {
  const { isEnglish, loginPath } = useLocale();
  const Icon = config.icon;

  return (
    <PublicPageShell eyebrow={config.eyebrow} title={config.title} description={config.description}>
      <section className="bg-[#F5F3E7] px-6 py-16">
        <div className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-3xl border border-[#E7E2CC] bg-white p-8 shadow-sm">
            <div className="mb-5 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-[#7A8B4A]/10 text-[#7A8B4A]">
              <Icon className="h-7 w-7" />
            </div>
            <h2 className="mb-4 text-3xl text-[#2C3419]">{isEnglish ? "When this scenario is especially useful" : "Когда этот сценарий особенно полезен"}</h2>
            <div className="space-y-3">
              {config.points.map((point) => (
                <div key={point} className="flex items-start gap-3 rounded-2xl bg-[#F5F3E7] p-4">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-[#7A8B4A]" />
                  <p className="text-sm leading-7 text-[#5A6B3A]">{point}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl bg-[#5A6B3A] p-8 text-white shadow-sm">
            <p className="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-white/70">{isEnglish ? "What the user gets" : "Что получит пользователь"}</p>
            <h2 className="mb-4 text-3xl">{config.resultTitle}</h2>
            <p className="mb-8 text-base leading-8 text-white/80">{config.resultDescription}</p>
            <Button
              asChild
              className="bg-white text-[#2C3419] hover:bg-white/90"
            >
              <Link
                to={loginPath}
                onClick={() => {
                  void trackPublicClick("use_case_page", "open_app_click", { route_key: config.routeKey });
                }}
              >
                {isEnglish ? "Try it in the app" : "Попробовать в приложении"}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-8 text-3xl text-[#2C3419] sm:text-4xl">{isEnglish ? "How the scenario works" : "Как проходит сценарий"}</h2>
          <div className="grid gap-6 md:grid-cols-3">
            {config.steps.map((step) => (
              <div key={step.title} className="rounded-2xl border border-[#E7E2CC] bg-[#F5F3E7] p-6">
                <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-[#7A8B4A] shadow-sm">
                  <step.icon className="h-6 w-6" />
                </div>
                <h3 className="mb-2 text-xl text-[#2C3419]">{step.title}</h3>
                <p className="text-sm leading-7 text-[#5A6B3A]">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#F5F3E7] px-6 py-16">
        <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-2">
          <div className="rounded-3xl border border-[#E7E2CC] bg-white p-8 shadow-sm">
            <h2 className="mb-6 text-3xl text-[#2C3419]">{isEnglish ? "What to prepare before launch" : "Что подготовить на входе"}</h2>
            <div className="space-y-3">
              {config.inputChecklist.map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-2xl bg-[#F5F3E7] p-4">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-[#7A8B4A]" />
                  <p className="text-sm leading-7 text-[#5A6B3A]">{item}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl border border-[#E7E2CC] bg-white p-8 shadow-sm">
            <h2 className="mb-6 text-3xl text-[#2C3419]">{isEnglish ? "What you will get" : "Что вы получите"}</h2>
            <div className="space-y-3">
              {config.outputChecklist.map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-2xl bg-[#F5F3E7] p-4">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-[#7A8B4A]" />
                  <p className="text-sm leading-7 text-[#5A6B3A]">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-8 text-3xl text-[#2C3419] sm:text-4xl">{isEnglish ? "Tips for a stronger result" : "Советы для лучшего результата"}</h2>
          <div className="grid gap-6 md:grid-cols-2">
            {config.advice.map((item) => (
              <div key={item} className="rounded-2xl border border-[#E7E2CC] bg-[#F5F3E7] p-6">
                <p className="text-sm leading-8 text-[#5A6B3A] sm:text-base">{item}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#F5F3E7] px-6 py-16">
        <div className="mx-auto max-w-5xl rounded-3xl border border-[#E7E2CC] bg-white p-8 shadow-sm">
          <h2 className="mb-4 text-3xl text-[#2C3419]">{isEnglish ? "If the result feels weak" : "Если результат оказался слабым"}</h2>
          <p className="text-base leading-8 text-[#5A6B3A]">
            {isEnglish
              ? "We do not want VizuAI to feel like a service that generates and disappears. If a result is genuinely weak, write to owner@vizuai.example or in Telegram. We can help with a rerun, promo code, or refund of the spent requests when the case really calls for it."
              : "Мы не хотим, чтобы VizuAI выглядел как сервис, который “сгенерировал и забыл”. Если результат получился неудачным по качеству, напишите нам на owner@vizuai.example или в Telegram. Мы готовы помочь с повторным запуском, промокодом или возвратом потраченных запросов, если ситуация действительно этого требует."}
          </p>
        </div>
      </section>
    </PublicPageShell>
  );
}

const interiorConfig: UseCaseConfig = {
  routeKey: "interior",
  eyebrow: "Сценарий",
  title: "Дизайн интерьера по фото",
  description: "Этот сценарий подходит тем, кто хочет загрузить фотографию комнаты и быстро получить новый вариант интерьера.",
  icon: Sparkles,
  points: [
    "Подходит, когда хочется быстро примерить новый стиль на своё помещение без долгой ручной визуализации.",
    "Удобен как первый шаг перед обсуждением палитры, мебели и общего направления ремонта.",
    "Помогает увидеть комнату по-новому, если пока сложно представить результат только по описанию.",
  ],
  steps: [
    {
      title: "Загрузите фото комнаты",
      description: "Лучше всего работают понятные фотографии помещения с хорошим светом и видимой геометрией комнаты.",
      icon: Upload,
    },
    {
      title: "Опишите задачу",
      description: "Можно указать стиль, палитру, настроение, пожелания по мебели или то, что важно сохранить без изменений.",
      icon: WandSparkles,
    },
    {
      title: "Получите новый вариант интерьера",
      description: "После обработки вы увидите экран результата, где можно скачать изображение, повторить запуск или перейти к поиску мебели.",
      icon: Sparkles,
    },
  ],
  resultTitle: "Новый вариант комнаты на основе вашего фото",
  resultDescription: "Главная ценность этого сценария — быстро превратить исходное фото в наглядный вариант обновлённого интерьера, не рисуя всё вручную и не объясняя идею только словами.",
  inputChecklist: [
    "Фотография комнаты с понятным ракурсом и достаточным светом.",
    "Короткое описание желаемого результата: стиль, настроение, цвета, материалы или пожелания по мебели.",
    "Если есть важные детали, которые нужно сохранить, лучше указать это прямо в запросе.",
  ],
  advice: [
    "Лучше работают фотографии, где хорошо видны стены, окна, мебель и общая геометрия помещения.",
    "Если комната сильно затемнена, перегружена мелкими предметами или снята с неудобного угла, результат может быть менее аккуратным.",
    "Не пытайтесь уместить в один запуск слишком много идей. Один понятный стиль обычно работает лучше, чем сразу несколько направлений.",
    "Если результат в целом близок, но хочется доработки, удобнее идти через повторный запуск или редактирование, а не переписывать задачу полностью.",
  ],
  outputChecklist: [
    "Готовый интерьерный рендер на основе вашего помещения.",
    "Возможность скачать результат, повторить запуск или перейти к поиску похожей мебели.",
    "Историю запуска внутри аккаунта, чтобы вернуться к нему позже.",
  ],
};

const referenceConfig: UseCaseConfig = {
  routeKey: "reference",
  eyebrow: "Сценарий",
  title: "Дизайн по референсу",
  description: "Этот сценарий подходит, когда у вас уже есть понравившееся изображение и вы хотите перенести его настроение или стиль на своё помещение.",
  icon: Palette,
  points: [
    "Нужен, когда обычного текстового описания недостаточно и хочется задать направление через конкретный визуальный образец.",
    "Хорошо подходит для ситуаций, когда важны не только цвета, но и общее настроение, материалы и характер интерьера.",
    "Помогает точнее донести визуальную идею, если в голове уже есть понравившийся пример.",
  ],
  steps: [
    {
      title: "Загрузите фото помещения",
      description: "Исходное фото остаётся базой, на которую сервис будет переносить новое настроение и стилистическое направление.",
      icon: Upload,
    },
    {
      title: "Добавьте изображение-референс",
      description: "Референс задаёт направление по цветам, материалам, атмосфере и общему ощущению пространства.",
      icon: ImageIcon,
    },
    {
      title: "Получите результат с ориентацией на стиль",
      description: "В результате вы увидите не только итоговую картинку, но и сам контекст запуска, чтобы позже можно было повторить сценарий.",
      icon: Palette,
    },
  ],
  resultTitle: "Редизайн с опорой на конкретный визуальный образец",
  resultDescription: "Этот сценарий нужен не просто для новой картинки, а для более точного движения в сторону выбранного визуального образца, когда настроение и стилистика важнее сухого описания.",
  inputChecklist: [
    "Фотография вашего помещения, которое нужно преобразить.",
    "Изображение-референс с тем стилем, атмосферой или материалами, которые вы хотите перенести.",
    "При желании — короткий текст с уточнениями: что важно сохранить, а что можно изменить смелее.",
  ],
  advice: [
    "Лучше выбирать референс, где стиль читается ясно: по цветам, мебели, свету, материалам и деталям.",
    "Сильнее всего этот сценарий помогает, когда хочется передать настроение, а не просто назвать стиль одним словом.",
    "Если исходное фото и референс слишком сильно расходятся по типу пространства, результат может быть менее убедительным.",
    "Хороший референс не обязан быть идеальной копией вашего помещения. Главное, чтобы он давал понятное визуальное направление.",
  ],
  outputChecklist: [
    "Результат, который опирается не только на текст, но и на конкретный визуальный образец.",
    "Отображение контекста запуска, чтобы позже можно было вернуться и повторить сценарий.",
    "Более управляемый и предсказуемый путь, если у вас уже есть понравившийся стиль.",
  ],
};

const furnitureConfig: UseCaseConfig = {
  routeKey: "furniture",
  eyebrow: "Сценарий",
  title: "Подбор мебели по фото",
  description: "Этот сценарий подходит, когда нужно по фотографии интерьера найти похожие предметы и перейти к готовым вариантам на маркетплейсах.",
  icon: Sofa,
  points: [
    "Полезен, когда хочется быстро найти похожий стул, стол, диван, светильник или другой предмет по фото.",
    "Помогает не только вдохновиться интерьером, но и перейти к реальным вариантам покупки.",
    "Особенно удобен после генерации дизайна, когда хочется понять, где искать похожую мебель.",
  ],
  steps: [
    {
      title: "Загрузите фото с мебелью",
      description: "Можно загрузить как крупный план одного предмета, так и целую комнату, где видно несколько объектов.",
      icon: Upload,
    },
    {
      title: "Сервис размечает объекты",
      description: "После запуска сервис выделяет предметы на изображении и собирает варианты для каждого объекта отдельно.",
      icon: Search,
    },
    {
      title: "Получите подборку ссылок",
      description: "В результате вы получаете группы товаров по объектам, чтобы сравнивать варианты не в одной общей ленте, а по смыслу.",
      icon: Sofa,
    },
  ],
  resultTitle: "Подборка похожих товаров по объектам на фото",
  resultDescription: "Финальный результат — это подборка ссылок по каждому найденному предмету, чтобы можно было быстро сравнить варианты и перейти от вдохновения к реальной покупке.",
  inputChecklist: [
    "Фотография комнаты или отдельного предмета, где мебель хорошо читается.",
    "Изображение без сильной размытости, перекрытий и слишком мелкого масштаба объекта.",
    "Лучше всего работают кадры, где предметы не сливаются друг с другом и не теряются на фоне.",
  ],
  advice: [
    "Если нужен конкретный предмет, лучше загружать кадр, где он виден крупнее и отделён от остальных объектов.",
    "Если в комнате много мебели, сервис всё равно постарается разделить предметы, но самые заметные обычно ищутся точнее.",
    "Это поиск похожих товаров, а не гарантия exact match. Иногда наилучший вариант будет близким по форме, а не идентичным по каждой детали.",
    "После генерации дизайна этот сценарий особенно полезен: так можно сразу перейти от понравившейся картинки к реальным вариантам покупки.",
  ],
  outputChecklist: [
    "Размеченное изображение с найденными объектами.",
    "Подборки ссылок по каждому предмету отдельно, а не одна общая мешанина товаров.",
    "Более быстрый путь от интерьерной идеи к реальным маркетплейсам.",
  ],
};

export function InteriorDesignPage() {
  const { isEnglish } = useLocale();
  const config = isEnglish
    ? {
        ...interiorConfig,
        eyebrow: "Scenario",
        title: "Interior design from photo",
        description: "This scenario is for people who want to upload a room photo and quickly get a new interior concept.",
        points: [
          "Useful when you want to preview a new style on your own room without slow manual visualization.",
          "A strong first step before discussing palette, furniture, and renovation direction.",
          "Helps you see the room differently when it is hard to imagine the result from words alone.",
        ],
        resultTitle: "A new room concept based on your original photo",
        resultDescription: "The main value of this scenario is turning a real room photo into a clear visual concept without drawing everything manually or explaining the idea only in words.",
        inputChecklist: [
          "A room photo with a clear angle and enough light.",
          "A short description of the target style, mood, colors, materials, or furniture wishes.",
          "If some details must stay untouched, mention that directly in the request.",
        ],
        advice: [
          "Photos work best when walls, windows, furniture, and room geometry are visible.",
          "If the room is too dark, cluttered, or shot from an awkward angle, the result can be less clean.",
          "Do not overload one run with too many directions. One clear style usually works better.",
          "If the result is close but needs improvement, rerun or edit is usually easier than rewriting the task from scratch.",
        ],
        outputChecklist: [
          "A finished interior render based on your actual room.",
          "Options to download the result, rerun it, or continue to furniture search.",
          "Saved history inside the account so you can return to it later.",
        ],
        steps: [
          {
            title: "Upload the room photo",
            description: "Photos work best when the room is clearly visible, well lit, and easy to read.",
            icon: Upload,
          },
          {
            title: "Describe the task",
            description: "You can specify style, palette, mood, furniture wishes, or what must stay unchanged.",
            icon: WandSparkles,
          },
          {
            title: "Get a new interior concept",
            description: "After processing, you see a result screen where you can download, rerun, or continue to furniture search.",
            icon: Sparkles,
          },
        ],
      }
    : interiorConfig;
  return <UseCasePage config={config} />;
}

export function DesignByReferencePage() {
  const { isEnglish } = useLocale();
  const config = isEnglish
    ? {
        ...referenceConfig,
        eyebrow: "Scenario",
        title: "Design by reference",
        description: "Use this scenario when you already have an inspiration image and want to transfer its mood or style to your own room.",
        points: [
          "Useful when plain text is not enough and you want to set direction through a concrete visual reference.",
          "Works well when mood, materials, and character matter as much as colors.",
          "Helps communicate a design idea more precisely when you already have a visual example in mind.",
        ],
        resultTitle: "A redesign guided by a specific inspiration image",
        resultDescription: "This scenario is not just about making a new picture. It helps move closer to a chosen visual direction when mood and style matter more than a dry text description.",
        inputChecklist: [
          "A photo of your room that should be redesigned.",
          "A reference image with the style, atmosphere, or materials you want to transfer.",
          "Optionally, a short text about what to keep and what can change more aggressively.",
        ],
        advice: [
          "Choose a reference where style is easy to read from colors, furniture, light, materials, and details.",
          "This scenario is especially useful when you want to transfer mood, not just name a style.",
          "If the room and the reference are radically different as spaces, the result can be less convincing.",
          "A strong reference does not need to match your room exactly. It only needs to provide a clear visual direction.",
        ],
        outputChecklist: [
          "A result driven by both text and a concrete visual reference.",
          "Visible launch context so you can revisit and rerun the scenario later.",
          "A more controllable path when you already know the style you like.",
        ],
        steps: [
          {
            title: "Upload your room photo",
            description: "The original room photo remains the base where the new mood and style are applied.",
            icon: Upload,
          },
          {
            title: "Add a reference image",
            description: "The reference sets direction for colors, materials, atmosphere, and the overall feeling of the space.",
            icon: ImageIcon,
          },
          {
            title: "Get the result in that style direction",
            description: "The result screen shows both the final image and the launch context so you can repeat it later.",
            icon: Palette,
          },
        ],
      }
    : referenceConfig;
  return <UseCasePage config={config} />;
}

export function FurnitureSearchPage() {
  const { isEnglish } = useLocale();
  const config = isEnglish
    ? {
        ...furnitureConfig,
        eyebrow: "Scenario",
        title: "Furniture search by photo",
        description: "Use this scenario when you want to find similar products from an interior image and jump to marketplace options faster.",
        points: [
          "Useful when you want to find a similar chair, table, sofa, light, or another object from a photo.",
          "Helps move from inspiration to real product choices instead of stopping at the visual idea.",
          "Especially practical after design generation when you want to search for similar furniture immediately.",
        ],
        resultTitle: "Grouped product links for objects found in the image",
        resultDescription: "The final result is a grouped selection of links for each detected object so you can compare options and move from inspiration to actual buying faster.",
        inputChecklist: [
          "A room photo or close-up where the furniture is clearly visible.",
          "An image without strong blur, occlusion, or objects that are too small in the frame.",
          "Best results come when the objects are visually separated and readable.",
        ],
        advice: [
          "If you care about one specific object, upload a shot where it is larger and less mixed with the rest of the room.",
          "When there is a lot of furniture, VizuAI still tries to split the objects, but the most visible items are usually matched more accurately.",
          "This is similar-product search, not a guaranteed exact match. Sometimes the best result will be close in shape and purpose rather than identical in every detail.",
          "After a design generation this scenario becomes especially useful because it helps jump straight from the image to real purchase options.",
        ],
        outputChecklist: [
          "An annotated image with detected objects.",
          "Separate link groups for each item instead of one mixed product stream.",
          "A faster bridge from interior inspiration to real marketplaces.",
        ],
        steps: [
          {
            title: "Upload a photo with visible furniture",
            description: "You can upload either a close-up of one object or a full room with several items.",
            icon: Upload,
          },
          {
            title: "The service marks the objects",
            description: "After launch, the service isolates items in the image and builds product groups per object.",
            icon: Search,
          },
          {
            title: "Get grouped marketplace links",
            description: "The output is organized by objects, so comparison is structured instead of mixed in one feed.",
            icon: Sofa,
          },
        ],
      }
    : furnitureConfig;
  return <UseCasePage config={config} />;
}
