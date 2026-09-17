import { useMemo, useState } from "react";
import { ArrowRight, MousePointerClick } from "lucide-react";
import { Link } from "react-router";

import configuredScreen from "@/assets/guides/reference/configured.png";
import inputPhoto from "@/assets/guides/reference/input-photo.jpg";
import referencePhoto from "@/assets/guides/reference/reference-photo.jpg";
import resultScreen from "@/assets/guides/reference/result.png";
import resultDetailScreen from "@/assets/guides/reference/result-detail.png";
import screenImage from "@/assets/guides/reference/screen.png";
import { GuidePromptCard, GuideShot, GuideStepSection } from "@/app/components/GuidePageBlocks";
import { PublicPageShell } from "@/app/components/PublicPageShell";
import { useLocale } from "@/app/i18n";
import { ResultImageViewer, type ViewerImage } from "@/app/components/ResultImageViewer";
import { Button } from "@/app/components/ui/button";
import { trackPublicClick } from "@/app/lib/analytics/client";

const referencePrompt =
  "Переделать ванную в стиле прованс. Цвета белый, голубой, цветочный принт. Теплый свет, латунная сантехника";

const inputTips = [
  "Сначала загрузите фото помещения, ниже добавьте референс",
  "В описании можно коротко уточнить цвета и детали",
];

const resultTips = ["На экране результата остаются и ваше фото, и референс"];

export function GuideReferencePage() {
  const { isEnglish, loginPath } = useLocale();
  const [viewerOpen, setViewerOpen] = useState(false);
  const [activeImageId, setActiveImageId] = useState<string | null>(null);

  const viewerImages = useMemo<ViewerImage[]>(
    () => [
      {
        id: "screen",
        label: "Экран сценария",
        alt: "Экран сценария дизайна по референсу",
        src: screenImage,
      },
      {
        id: "input",
        label: "Фото помещения",
        alt: "Исходное фото помещения для дизайна по референсу",
        src: inputPhoto,
      },
      {
        id: "reference",
        label: "Референс",
        alt: "Изображение-референс для переноса стиля",
        src: referencePhoto,
      },
      {
        id: "configured",
        label: "Фото, референс и запрос",
        alt: "Экран сценария с загруженным фото, референсом и текстом запроса",
        src: configuredScreen,
      },
      {
        id: "result",
        label: "Готовый экран",
        alt: "Готовый экран результата дизайна по референсу",
        src: resultScreen,
      },
      {
        id: "result-detail",
        label: "Готовый результат",
        alt: "Крупный просмотр результата дизайна по референсу",
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
      title={isEnglish ? "How to redesign by reference in VizuAI" : "Как сделать дизайн по референсу в VizuAI"}
      description={isEnglish ? "Upload your room, add a reference image, and get a new interior in the target mood" : "Загрузите фото своего помещения, добавьте референс и получите новый вариант интерьера в нужном настроении"}
    >
      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-6xl space-y-12">
          <GuideStepSection
            step={isEnglish ? "Step 1" : "Шаг 1"}
            title={isEnglish ? "Open the design-by-reference scenario" : "Откройте сценарий дизайна по референсу"}
            description={isEnglish ? "In this mode you upload two images: your room and a reference image." : "В этом режиме вы загружаете два изображения: своё помещение и картинку-референс."}
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="screen"
                  src={screenImage}
                  alt="Экран сценария дизайна по референсу"
                  label="Экран сценария"
                  title="Стартовый экран"
                  description="Здесь есть отдельные поля для помещения, референса и запроса"
                  onOpen={openViewer}
                />
              </div>
            }
          />

          <GuideStepSection
            step={isEnglish ? "Step 2" : "Шаг 2"}
            title={isEnglish ? "Upload the room, the reference, and add your notes" : "Загрузите помещение, референс и добавьте пожелания"}
            description={isEnglish ? "Your room photo defines the space, and the reference sets style and mood" : "Своё фото задаёт пространство, а референс — стиль и настроение"}
            tips={inputTips}
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="input"
                  src={inputPhoto}
                  alt="Исходное фото помещения для дизайна по референсу"
                  label="Фото помещения"
                  title="Ваше помещение"
                  description="Это фото задаёт пространство"
                  imageClassName="object-cover"
                  onOpen={openViewer}
                />
                <GuideShot
                  imageId="reference"
                  src={referencePhoto}
                  alt="Изображение-референс для переноса стиля"
                  label="Референс"
                  title="Стиль и настроение"
                  description="Референс помогает показать цвета, материалы и настроение"
                  imageClassName="bg-[#F5F3E7] object-cover"
                  onOpen={openViewer}
                />
                <GuideShot
                  imageId="configured"
                  src={configuredScreen}
                  alt="Экран сценария с загруженным фото, референсом и текстом запроса"
                  label="После загрузки"
                  title="Готово к запуску"
                  description="Когда оба изображения на месте, можно уточнить детали и запускать"
                  onOpen={openViewer}
                />
                <GuidePromptCard title={isEnglish ? "Example prompt" : "Пример запроса"} prompt={referencePrompt} />
              </div>
            }
          />

          <GuideStepSection
            step={isEnglish ? "Step 3" : "Шаг 3"}
            title={isEnglish ? "Get the result in the reference style direction" : "Получите результат в стиле референса"}
            description={isEnglish ? "After generation VizuAI shows the result in the intended mood" : "После генерации VizuAI покажет результат в нужном настроении"}
            tips={resultTips}
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="result"
                  src={resultScreen}
                  alt="Готовый экран результата дизайна по референсу"
                  label="Готовый экран"
                  title="Результат на отдельной странице"
                  description="Здесь видно помещение, референс и результат"
                  onOpen={openViewer}
                />
                <GuideShot
                  imageId="result-detail"
                  src={resultDetailScreen}
                  alt="Крупный просмотр результата дизайна по референсу"
                  label="Крупный просмотр"
                  title="Новый интерьер в нужном настроении"
                  description="Готовое изображение можно раскрыть и спокойно рассмотреть"
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
          <h2 className="mb-3 text-3xl text-[#2C3419]">{isEnglish ? "Want to try it with your own reference?" : "Хотите попробовать со своим референсом?"}</h2>
          <p className="mb-8 text-base leading-8 text-[#5A6B3A]">
            {isEnglish ? "Upload your room, add an inspiration image, and get a version in the target style" : "Загрузите фото помещения, добавьте пример понравившегося интерьера и получите свой вариант в нужном стиле"}
          </p>
          <Button asChild className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]">
            <Link
              to={loginPath}
              onClick={() => {
                void trackPublicClick("guide_reference", "bottom_cta_click");
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
