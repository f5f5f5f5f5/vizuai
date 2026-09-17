import { useMemo, useState } from "react";
import { ArrowRight, MousePointerClick } from "lucide-react";
import { Link } from "react-router";

import configuredScreen from "@/assets/guides/design/configured.png";
import inputPhoto from "@/assets/guides/design/input-photo.jpg";
import resultDetailScreen from "@/assets/guides/design/result-detail.png";
import resultScreen from "@/assets/guides/design/result.png";
import screenImage from "@/assets/guides/design/screen.png";
import { GuidePromptCard, GuideShot, GuideStepSection } from "@/app/components/GuidePageBlocks";
import { PublicPageShell } from "@/app/components/PublicPageShell";
import { useLocale } from "@/app/i18n";
import { ResultImageViewer, type ViewerImage } from "@/app/components/ResultImageViewer";
import { Button } from "@/app/components/ui/button";
import { trackPublicClick } from "@/app/lib/analytics/client";

const designPrompt =
  "Переделать гостиную в стиле бохо. Поменять пол, диван, ковер, люстру. Добавить акцентных элементов: растения, панно из веревок. Тип комнаты: гостиная. Цвета: бежевый, зеленый, охра";

const inputTips = [
  "Лучше сразу назвать тип комнаты, стиль, цвета и главные изменения",
];

const resultTips = ["С этого же результата можно перейти к поиску мебели"];

export function GuideDesignPhotoPage() {
  const { isEnglish, loginPath } = useLocale();
  const [viewerOpen, setViewerOpen] = useState(false);
  const [activeImageId, setActiveImageId] = useState<string | null>(null);

  const viewerImages = useMemo<ViewerImage[]>(
    () => [
      {
        id: "screen",
        label: "Экран сценария",
        alt: "Экран дизайна интерьера до загрузки фото",
        src: screenImage,
      },
      {
        id: "input",
        label: "Фото комнаты",
        alt: "Пример исходной фотографии комнаты для редизайна",
        src: inputPhoto,
      },
      {
        id: "configured",
        label: "Фото и запрос",
        alt: "Экран дизайна интерьера с загруженной фотографией и готовым запросом",
        src: configuredScreen,
      },
      {
        id: "result",
        label: "Готовый результат",
        alt: "Готовый экран результата дизайна интерьера",
        src: resultScreen,
      },
      {
        id: "result-detail",
        label: "Результат крупно",
        alt: "Крупный просмотр результата дизайна интерьера",
        src: resultDetailScreen,
      },
    ],
    [],
  );

  const openViewer = (imageId: string) => {
    setActiveImageId(imageId);
    setViewerOpen(true);
  };

  return (
    <PublicPageShell
      eyebrow={isEnglish ? "Step by step" : "Пошагово"}
      title={isEnglish ? "How to design an interior from a photo in VizuAI" : "Как сделать дизайн интерьера по фото в VizuAI"}
      description={isEnglish ? "Open the scenario, upload a room photo, describe the target style, and get a finished render" : "Откройте сценарий, загрузите фото комнаты, опишите желаемый стиль и получите готовый интерьерный рендер"}
    >
      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-6xl space-y-12">
          <GuideStepSection
            step={isEnglish ? "Step 1" : "Шаг 1"}
            title={isEnglish ? "Open the interior design scenario" : "Откройте сценарий дизайна интерьера"}
            description=""
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="screen"
                  src={screenImage}
                  alt="Экран дизайна интерьера до загрузки фото"
                  label="Экран сценария"
                  title="Стартовый экран"
                  description="Здесь вы загружаете фото комнаты и добавляете пожелания"
                  onOpen={openViewer}
                />
              </div>
            }
          />

          <GuideStepSection
            step={isEnglish ? "Step 2" : "Шаг 2"}
            title={isEnglish ? "Upload the room photo and describe what should change" : "Загрузите фото комнаты и опишите, что хотите изменить"}
            description={isEnglish ? "Upload one room photo and briefly describe the target changes" : "Загрузите одно фото комнаты и коротко опишите, что хотите изменить"}
            tips={inputTips}
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="input"
                  src={inputPhoto}
                  alt="Пример исходной фотографии комнаты для редизайна"
                  label="Фото комнаты"
                  title="Подготовьте понятный кадр"
                  description="Лучше выбирать фото, где комнату хорошо видно целиком"
                  imageClassName="object-cover"
                  onOpen={openViewer}
                />
                <GuideShot
                  imageId="configured"
                  src={configuredScreen}
                  alt="Экран дизайна интерьера с загруженной фотографией и готовым запросом"
                  label="После загрузки"
                  title="Добавьте пожелания"
                  description="Опишите стиль, цвета и основные изменения"
                  onOpen={openViewer}
                />
                <GuidePromptCard title={isEnglish ? "Example prompt" : "Пример запроса"} prompt={designPrompt} />
              </div>
            }
          />

          <GuideStepSection
            step={isEnglish ? "Step 3" : "Шаг 3"}
            title={isEnglish ? "Launch the run and open the result" : "Запустите генерацию и откройте результат"}
            description={isEnglish ? "After generation you get a finished render in the new style" : "После генерации вы получите готовый рендер в новом стиле"}
            tips={resultTips}
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="result"
                  src={resultScreen}
                  alt="Готовый экран результата дизайна интерьера"
                  label="Готовый экран"
                  title="Результат на отдельной странице"
                  description="Здесь видно исходное фото, описание и результат"
                  onOpen={openViewer}
                />
                <GuideShot
                  imageId="result-detail"
                  src={resultDetailScreen}
                  alt="Крупный просмотр результата дизайна интерьера"
                  label="Крупный просмотр"
                  title="Рассмотрите результат крупно"
                  description="Изображение можно раскрыть и спокойно посмотреть детали"
                  onOpen={openViewer}
                />
              </div>
            }
          />
        </div>
      </section>

      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-5xl rounded-3xl border border-[#E7E2CC] bg-[#F5F3E7] p-8 text-center">
          <div className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-[#7A8B4A] shadow-sm">
            <MousePointerClick className="h-7 w-7" />
          </div>
          <h2 className="mb-3 text-3xl text-[#2C3419]">{isEnglish ? "Want to try it on your own room?" : "Хотите попробовать на своём фото?"}</h2>
          <p className="mb-8 text-base leading-8 text-[#5A6B3A]">
            {isEnglish ? "Open the app, upload your room, and describe the style you want. VizuAI will build a new interior concept from your photo" : "Откройте приложение, загрузите комнату и опишите желаемый стиль. VizuAI соберёт новый вариант интерьера по вашему кадру"}
          </p>
          <Button asChild className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]">
            <Link
              to={loginPath}
              onClick={() => {
                void trackPublicClick("guide_design_photo", "bottom_cta_click");
              }}
            >
              {isEnglish ? "Open the app" : "Перейти в приложение"}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </section>

      <ResultImageViewer
        open={viewerOpen}
        onOpenChange={setViewerOpen}
        images={viewerImages}
        activeImageId={activeImageId}
        onActiveImageChange={setActiveImageId}
      />
    </PublicPageShell>
  );
}
