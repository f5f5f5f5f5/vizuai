import { useMemo, useState } from "react";
import { ArrowRight, MousePointerClick } from "lucide-react";
import { Link } from "react-router";

import closeupPhoto from "@/assets/guides/furniture/closeup.png";
import inputPhoto from "@/assets/guides/furniture/input-photo.jpg";
import resultScreen from "@/assets/guides/furniture/result.png";
import searchScreen from "@/assets/guides/furniture/search-screen.png";
import uploadedScreen from "@/assets/guides/furniture/uploaded.png";
import { PublicPageShell } from "@/app/components/PublicPageShell";
import { GuideShot, GuideStepSection } from "@/app/components/GuidePageBlocks";
import { useLocale } from "@/app/i18n";
import { ResultImageViewer, type ViewerImage } from "@/app/components/ResultImageViewer";
import { Button } from "@/app/components/ui/button";
import { trackPublicClick } from "@/app/lib/analytics/client";

const inputTips = ["Если нужен один предмет, крупный план обычно работает точнее"];

const resultTips = ["Результат сразу разложен по объектам: каждый предмет в своей группе"];

export function GuideFurnitureSearchPage() {
  const { isEnglish, loginPath } = useLocale();
  const [viewerOpen, setViewerOpen] = useState(false);
  const [activeImageId, setActiveImageId] = useState<string | null>(null);

  const viewerImages = useMemo<ViewerImage[]>(
    () => [
      {
        id: "search",
        label: "Экран поиска",
        alt: "Экран поиска мебели до загрузки фото",
        src: searchScreen,
      },
      {
        id: "input",
        label: "Пример фото",
        alt: "Пример исходной фотографии интерьера для поиска мебели",
        src: inputPhoto,
      },
      {
        id: "uploaded",
        label: "Фото загружено",
        alt: "Экран поиска мебели с уже загруженной фотографией",
        src: uploadedScreen,
      },
      {
        id: "result",
        label: "Готовый результат",
        alt: "Готовый экран результата поиска мебели с карточками товаров",
        src: resultScreen,
      },
      {
        id: "closeup",
        label: "Крупный просмотр",
        alt: "Крупный просмотр результата поиска мебели",
        src: closeupPhoto,
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
      title={isEnglish ? "How to find furniture from an interior photo in VizuAI" : "Как искать мебель по фото интерьера в VizuAI"}
      description={isEnglish ? "Three simple steps: open the search, upload a photo, and get grouped results by detected objects" : "Три простых шага: открыть поиск, загрузить фото и получить готовые подборки по найденным предметам"}
    >
      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-6xl space-y-12">
          <GuideStepSection
            step={isEnglish ? "Step 1" : "Шаг 1"}
            title={isEnglish ? "Open the app and choose the furniture search scenario" : "Откройте приложение и выберите сценарий поиска мебели"}
            description={isEnglish ? "Open the Furniture Search section. On the next screen you can upload a photo and start right away" : "Откройте раздел «Поиск мебели». На следующем экране можно сразу загрузить фото и запустить поиск"}
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="search"
                  src={searchScreen}
                  alt="Экран поиска мебели до загрузки фото"
                  label="Экран поиска"
                  title="Экран запуска"
                  description="Здесь всё начинается"
                  onOpen={openViewer}
                />
              </div>
            }
          />

          <GuideStepSection
            step={isEnglish ? "Step 2" : "Шаг 2"}
            title={isEnglish ? "Upload a photo where the furniture is clearly visible" : "Загрузите фото, на котором мебель хорошо читается"}
            description={isEnglish ? "Both a full-room shot and a close-up of one item can work" : "Подойдёт и общий кадр комнаты, и один предмет крупным планом"}
            tips={inputTips}
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="input"
                  src={inputPhoto}
                  alt="Пример исходной фотографии интерьера для поиска мебели"
                  label="Пример входного фото"
                  title="Можно загрузить и общий интерьер"
                  description="Если предметы хорошо видны, сервис соберёт подборки по каждому объекту"
                  imageClassName="object-cover"
                  onOpen={openViewer}
                />
                <GuideShot
                  imageId="uploaded"
                  src={uploadedScreen}
                  alt="Экран поиска мебели с уже загруженной фотографией"
                  label="После загрузки"
                  title="Проверьте кадр перед запуском"
                  description="Если всё выглядит хорошо, можно запускать"
                  onOpen={openViewer}
                />
              </div>
            }
          />

          <GuideStepSection
            step={isEnglish ? "Step 3" : "Шаг 3"}
            title={isEnglish ? "Run the search and wait for the result" : "Запустите поиск и дождитесь готового результата"}
            description={isEnglish ? "You will get grouped links for each detected object" : "На выходе вы получите готовые ссылки по каждому найденному предмету"}
            tips={resultTips}
            gallery={
              <div className="space-y-6">
                <GuideShot
                  imageId="result"
                  src={resultScreen}
                  alt="Готовый экран результата поиска мебели с карточками товаров"
                  label="Готовый результат"
                  title="Подборки по каждому предмету"
                  description="По товарам можно сразу перейти на маркетплейсы"
                  onOpen={openViewer}
                />
                <GuideShot
                  imageId="closeup"
                  src={closeupPhoto}
                  alt="Крупный просмотр результата поиска мебели"
                  label="Крупный просмотр"
                  title="Если хотите посмотреть ближе"
                  description="Результат можно раскрыть и проверить разметку объектов"
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
          <h2 className="mb-3 text-3xl text-[#2C3419]">{isEnglish ? "Want to try it on your own image?" : "Хотите попробовать на своём изображении?"}</h2>
          <p className="mb-8 text-base leading-8 text-[#5A6B3A]">{isEnglish ? "Open the app, upload a photo, and run furniture search on your own interior" : "Откройте приложение, загрузите фото и запустите поиск мебели по своему интерьеру"}</p>
          <Button
            asChild
            className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
          >
            <Link
              to={loginPath}
              onClick={() => {
                void trackPublicClick("guide_furniture", "bottom_cta_click");
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
