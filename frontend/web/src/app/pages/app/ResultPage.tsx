import { useEffect, useMemo, useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router";
import {
  ArrowLeft, Loader2, CheckCircle, ExternalLink, Download, RotateCw,
  Edit, Search, XCircle, HelpCircle, Clock, Zap, PackageX,
} from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { useTheme } from "@/app/contexts/ThemeContext";
import { AppImage } from "@/app/components/AppImage";
import { ResultImageViewer, ZoomableImageCard, type ViewerImage } from "@/app/components/ResultImageViewer";
import { api, type DesignResult, type FurnitureResult, type HistoryItem, type JobSnapshot } from "@/app/lib/api";
import { toUiJobStatus } from "@/app/lib/jobStatus";

type ResultMode = "design" | "reference" | "furniture";

type FurnitureProductView = {
  title: string;
  marketplace: string | null;
  url: string | null;
  image_url: string | null;
  price: string | null;
  match_score: number | null;
};

type FurnitureCardView = {
  title: string;
  products: FurnitureProductView[];
};

function formatMarketplaceLabel(value: string | null | undefined): string | null {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (normalized === "wildberries") return "WB";
  if (normalized === "yandex_market") return "Яндекс Маркет";
  if (normalized === "ozon") return "OZON";
  return normalized;
}

function normalizeFurnitureCard(objectCard: Record<string, unknown>, index: number): FurnitureCardView {
  const title = String(
    objectCard.object_name ||
      objectCard.label ||
      `Объект ${index + 1}`,
  );

  const directProducts = Array.isArray(objectCard.products) ? objectCard.products : [];
  if (directProducts.length > 0) {
    return {
      title,
      products: directProducts.map((product, productIndex) => {
        const item = (product || {}) as Record<string, unknown>;
        return {
          title: String(item.title || item.label || `${title} ${productIndex + 1}`),
          marketplace: formatMarketplaceLabel(String(item.marketplace || item.source || "")),
          url: String(item.url || "") || null,
          image_url: String(item.image_url || item.image || "") || null,
          price: String(item.price || "") || null,
          match_score: typeof item.match_score === "number" ? Number(item.match_score) : null,
        };
      }),
    };
  }

  const rankedLinks = Array.isArray(objectCard.ranked_links) ? objectCard.ranked_links : [];
  if (rankedLinks.length > 0) {
    const products = rankedLinks
      .flatMap((entry, linkIndex) => {
        const item = (entry || {}) as Record<string, unknown>;
        const url = String(item.url || "").trim();
        if (!url) {
          return [];
        }
        const marketplace = formatMarketplaceLabel(String(item.marketplace || ""));
        const score = typeof item.match_score === "number" ? Number(item.match_score) : null;
        const productTitle = String(item.title || "").trim();
        const imageUrl = String(item.image_url || "").trim();
        return [{
          title: productTitle || marketplace || `Ссылка ${linkIndex + 1}`,
          marketplace,
          url,
          image_url: imageUrl || null,
          price: null,
          match_score: score,
        }];
      })
      .sort((left, right) => {
        const leftScore = left.match_score ?? -1;
        const rightScore = right.match_score ?? -1;
        if (leftScore !== rightScore) {
          return rightScore - leftScore;
        }
        return (left.marketplace || "").localeCompare(right.marketplace || "", "ru");
      });

    return {
      title,
      products,
    };
  }

  const links = objectCard.links && typeof objectCard.links === "object" ? (objectCard.links as Record<string, unknown>) : {};
  const fallbackProducts = Object.entries(links).flatMap(([marketplaceKey, values]) => {
    if (!Array.isArray(values)) {
      return [];
    }
    return values.flatMap((value, linkIndex) => {
      const url = String(value || "").trim();
      if (!url) {
        return [];
      }
      const marketplace = formatMarketplaceLabel(marketplaceKey);
      return [{
        title: marketplace || `Ссылка ${linkIndex + 1}`,
        marketplace,
        url,
        image_url: null,
        price: null,
        match_score: null,
      }];
    });
  });

  return {
    title,
    products: fallbackProducts,
  };
}

export function ResultPage() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { isDarkMode } = useTheme();
  const stateJobId = location.state?.jobId as string | undefined;

  const [jobSnapshot, setJobSnapshot] = useState<JobSnapshot | null>(null);
  const [historyItem, setHistoryItem] = useState<HistoryItem | null>(null);
  const [designResult, setDesignResult] = useState<DesignResult | null>(null);
  const [furnitureResult, setFurnitureResult] = useState<FurnitureResult | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [activeViewerImageId, setActiveViewerImageId] = useState<string | null>(null);
  const [status, setStatus] = useState<"loading" | "processing" | "completed" | "failed">(
    stateJobId ? "processing" : "loading",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const stateMode = location.state?.mode as ResultMode | undefined;
  const stateInputImage = location.state?.inputImage as string | undefined;
  const stateReferenceImage = location.state?.referenceImage as string | undefined;
  const statePrompt = location.state?.prompt as string | undefined;

  useEffect(() => {
    if (!id) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    const loadResult = async (resultId: string) => {
      try {
        const item = await api.getHistoryItem(resultId);
        if (cancelled) return;

        setHistoryItem(item);
        setStatus(toUiJobStatus(item.status));

        if (item.mode === "furniture_search") {
          const result = await api.getFurnitureResult(resultId);
          if (!cancelled) {
            setStatus("completed");
            setFurnitureResult(result);
            setDesignResult(null);
          }
          return;
        }

        const result = await api.getDesignResult(resultId);
        if (!cancelled) {
          setStatus("completed");
          setDesignResult(result);
          setFurnitureResult(null);
        }
      } catch (error) {
        console.error("Failed to load result:", error);
        if (!cancelled) {
          setStatus("failed");
          setErrorMessage("Не удалось загрузить результат.");
        }
      }
    };

    const pollJob = async (jobId: string) => {
      try {
        const job = await api.getJob(jobId);
        if (cancelled) return;

        setJobSnapshot(job);

        if (job.status === "completed" && job.result_ref_id) {
          navigate(`/app/workspace/result/${job.result_ref_id}`, {
            replace: true,
            state: {
              mode: stateMode,
              inputImage: stateInputImage,
              referenceImage: stateReferenceImage,
              prompt: statePrompt,
            },
          });
          return;
        }

        if (job.status === "failed") {
          setStatus("failed");
          setErrorMessage(job.error_message || "Запрос завершился с ошибкой.");
          return;
        }

        setStatus("processing");
        timer = window.setTimeout(() => {
          void pollJob(jobId);
        }, 2500);
      } catch (error) {
        console.error("Failed to poll job:", error);
        if (!cancelled) {
          setStatus("failed");
          setErrorMessage("Не удалось получить статус запроса.");
        }
      }
    };

    if (stateJobId) {
      void pollJob(stateJobId);
    } else {
      void loadResult(id);
    }

    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [id, navigate, stateInputImage, stateJobId, stateMode, statePrompt, stateReferenceImage]);

  const resolvedMode = useMemo<ResultMode>(() => {
    const mode = historyItem?.mode || designResult?.mode || furnitureResult?.mode || stateMode;
    if (mode === "furniture_search" || mode === "furniture") return "furniture";
    if (mode === "reference") return "reference";
    return "design";
  }, [historyItem, designResult, furnitureResult, stateMode]);

  const effectiveStatus = useMemo<"loading" | "processing" | "completed" | "failed">(() => {
    if (designResult || furnitureResult) {
      return "completed";
    }
    if (errorMessage && status !== "loading") {
      return "failed";
    }
    return status;
  }, [designResult, furnitureResult, errorMessage, status]);

  const statusMessages = {
    loading: {
      design: "Загружаем результат...",
      reference: "Загружаем результат...",
      furniture: "Загружаем результат...",
    },
    processing: {
      design: "Создаем дизайн вашего интерьера...",
      reference: "Применяем референс к вашему помещению...",
      furniture: "Ищем похожую мебель на маркетплейсах...",
    },
    completed: {
      design: "Дизайн готов!",
      reference: "Дизайн готов!",
      furniture: "Поиск завершен!",
    },
    failed: {
      design: "Произошла ошибка",
      reference: "Произошла ошибка",
      furniture: "Произошла ошибка",
    },
  };

  const pageTitles: Record<ResultMode, string> = {
    design: "Дизайн интерьера",
    reference: "Дизайн по референсу",
    furniture: "Поиск мебели",
  };

  const inputImage =
    designResult?.original_image_url ||
    furnitureResult?.original_image_url ||
    historyItem?.original_image_url ||
    stateInputImage ||
    "";
  const referenceImage =
    designResult?.style_reference_image_url ||
    stateReferenceImage ||
    "";
  const prompt = historyItem?.user_request || designResult?.user_request || furnitureResult?.user_request || statePrompt || "";
  const metadataTime = historyItem?.ended_at || designResult?.ended_at || furnitureResult?.ended_at || null;
  const unitsSpent = historyItem?.units_spent || designResult?.units_spent || furnitureResult?.units_spent || 1;
  const resultImage =
    designResult?.final_image_url ||
    designResult?.render_image_url ||
    designResult?.fix_image_url ||
    furnitureResult?.final_image_url ||
    null;
  const viewerImages = useMemo<ViewerImage[]>(() => {
    const images: ViewerImage[] = [];
    if (resultImage) {
      images.push({ id: "result", label: "Результат", alt: "Result", src: resultImage });
    }
    if (inputImage) {
      images.push({
        id: "input",
        label: resolvedMode === "furniture" ? "Фото мебели" : "Фото помещения",
        alt: "Input",
        src: inputImage,
      });
    }
    if (referenceImage) {
      images.push({ id: "reference", label: "Референс", alt: "Reference", src: referenceImage });
    }
    return images;
  }, [inputImage, referenceImage, resolvedMode, resultImage]);

  useEffect(() => {
    if (!viewerImages.length) {
      if (activeViewerImageId !== null) {
        setActiveViewerImageId(null);
      }
      return;
    }
    if (!activeViewerImageId || !viewerImages.some((image) => image.id === activeViewerImageId)) {
      setActiveViewerImageId(viewerImages[0].id);
    }
  }, [activeViewerImageId, viewerImages]);

  const handleBack = () => {
    navigate(`/app/workspace?mode=${resolvedMode}`);
  };

  const handleRepeat = () => {
    if (!historyItem?.id && !designResult?.id && !furnitureResult?.id) {
      navigate(`/app/workspace?mode=${resolvedMode}`);
      return;
    }
    const resultId = historyItem?.id || designResult?.id || furnitureResult?.id;
    navigate(`/app/workspace?mode=${resolvedMode}`, {
      state: { reuseResultId: resultId },
    });
  };

  const handleEdit = () => {
    const resultId = historyItem?.id || designResult?.id;
    navigate(`/app/workspace?mode=${resolvedMode}`, {
      state: { editResultId: resultId },
    });
  };

  const handleSearchFurniture = () => {
    const resultId = historyItem?.id || designResult?.id || furnitureResult?.id;
    if (!resultId) {
      navigate("/app/workspace?mode=furniture");
      return;
    }
    if (resolvedMode !== "furniture") {
      navigate("/app/workspace?mode=furniture", {
        state: { furnitureSeedResultId: resultId },
      });
      return;
    }
    navigate("/app/workspace?mode=furniture", {
      state: { reuseResultId: resultId },
    });
  };

  const handleDownload = async () => {
    if (!resultImage || !id) {
      return;
    }

    try {
      const blob =
        resolvedMode === "furniture"
          ? await api.downloadFurnitureResult(id)
          : await api.downloadDesignResult(id);
      const blobUrl = window.URL.createObjectURL(blob);
      const extension = blob.type === "image/png" ? "png" : blob.type === "image/webp" ? "webp" : "jpg";
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `vizuai-result-${id.slice(0, 8)}.${extension}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => {
        window.URL.revokeObjectURL(blobUrl);
      }, 1000);
    } catch (error) {
      console.error("Failed to download result:", error);
      window.alert("Не удалось скачать изображение. Попробуйте еще раз.");
    }
  };

  const openViewer = (imageId: string) => {
    setActiveViewerImageId(imageId);
    setViewerOpen(true);
  };

  return (
    <div className="h-full flex flex-col">
      <div className={`border-b px-4 py-5 sm:px-8 sm:py-6 ${isDarkMode ? "border-gray-800" : "border-gray-200"}`}>
        <div className="mx-auto flex max-w-7xl flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4 sm:items-center">
            <Button
              variant="outline"
              onClick={handleBack}
              className={isDarkMode ? "border-gray-700 bg-gray-900 text-gray-200 hover:bg-gray-800 hover:text-white" : "border-gray-300 text-gray-700 hover:bg-gray-50"}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Назад
            </Button>
            <div>
              <h1 className={`mb-1 text-xl font-bold sm:text-2xl ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                {pageTitles[resolvedMode]}
              </h1>
              <div className="flex items-center gap-2">
                {(effectiveStatus === "loading" || effectiveStatus === "processing") && <Loader2 className="w-4 h-4 text-[#7A8B4A] animate-spin" />}
                {effectiveStatus === "completed" && <CheckCircle className="w-4 h-4 text-green-500" />}
                {effectiveStatus === "failed" && <XCircle className="w-4 h-4 text-red-500" />}
                <span className={`text-sm ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
                  {statusMessages[effectiveStatus][resolvedMode]}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="mx-auto max-w-7xl p-4 sm:p-8">
          {(effectiveStatus === "loading" || effectiveStatus === "processing") && (
            <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
              <div className="space-y-6">
                <div className={`rounded-2xl p-5 sm:p-6 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
                  <h3 className={`text-lg font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Вводные данные</h3>

                  {inputImage && (
                    <div className="space-y-3 mb-4">
                      <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                        {resolvedMode === "furniture" ? "Фото мебели" : "Фото помещения"}
                      </label>
                      <div className="rounded-xl overflow-hidden border border-gray-700">
                        <ZoomableImageCard
                          src={inputImage}
                          alt="Input"
                          label={resolvedMode === "furniture" ? "Фото мебели" : "Фото помещения"}
                          className="h-40 w-full object-cover sm:h-48"
                          fallbackClassName="flex h-40 w-full items-center justify-center bg-gray-100 text-center text-gray-500 sm:h-48"
                          onOpen={() => openViewer("input")}
                        />
                      </div>
                    </div>
                  )}

                  {referenceImage && (
                    <div className="space-y-3 mb-4">
                      <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>Референс</label>
                      <div className="rounded-xl overflow-hidden border border-gray-700">
                        <ZoomableImageCard
                          src={referenceImage}
                          alt="Reference"
                          label="Референс"
                          className="h-40 w-full object-cover sm:h-48"
                          fallbackClassName="flex h-40 w-full items-center justify-center bg-gray-100 text-center text-gray-500 sm:h-48"
                          onOpen={() => openViewer("reference")}
                        />
                      </div>
                    </div>
                  )}

                  {prompt && (
                    <div className="space-y-3">
                      <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>Описание</label>
                      <div className={`rounded-xl border p-4 text-sm ${
                        isDarkMode ? "bg-gray-900 border-gray-700 text-gray-300" : "bg-gray-50 border-gray-200 text-gray-700"
                      }`}>
                        {prompt}
                      </div>
                    </div>
                  )}
                </div>

                <div className={`rounded-2xl p-5 sm:p-6 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
                  <h3 className={`text-lg font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Информация</h3>
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <Clock className={`w-4 h-4 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`} />
                      <div>
                        <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-600"}`}>Статус</p>
                        <p className={`text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                          {statusMessages[effectiveStatus][resolvedMode]}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Zap className={`w-4 h-4 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`} />
                      <div>
                        <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-600"}`}>Сценарий</p>
                        <p className={`text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                          {pageTitles[resolvedMode]}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-6 lg:col-span-2">
                <div className={`rounded-2xl p-6 sm:p-8 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
                  <div className="flex flex-col items-start gap-5 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="mb-3 flex items-center gap-3">
                        <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${
                          isDarkMode ? "bg-[#7A8B4A]/15 text-[#A8BE63]" : "bg-[#7A8B4A]/10 text-[#7A8B4A]"
                        }`}>
                          <Loader2 className="h-6 w-6 animate-spin" />
                        </div>
                        <div>
                          <h3 className={`text-xl font-semibold ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                            {statusMessages[effectiveStatus][resolvedMode]}
                          </h3>
                          <p className={`text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                            {effectiveStatus === "processing"
                              ? "Оставьте страницу открытой. Результат появится здесь автоматически."
                              : "Подготавливаем данные и собираем экран результата."}
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className={`w-full max-w-xs rounded-2xl border px-4 py-3 sm:w-auto ${
                      isDarkMode ? "border-gray-800 bg-gray-900" : "border-gray-200 bg-gray-50"
                    }`}>
                      <p className={`text-xs uppercase tracking-[0.16em] ${isDarkMode ? "text-gray-500" : "text-gray-500"}`}>Состояние</p>
                      <p className={`mt-1 text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                        {effectiveStatus === "processing" ? "В работе" : "Загрузка"}
                      </p>
                    </div>
                  </div>

                  <div className="mt-8">
                    <div className={`h-2 overflow-hidden rounded-full ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`}>
                      <div className="h-full rounded-full bg-[#7A8B4A] animate-pulse" style={{ width: effectiveStatus === "processing" ? "60%" : "35%" }} />
                    </div>
                  </div>

                  <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className={`rounded-2xl border p-4 ${isDarkMode ? "border-gray-800 bg-gray-900" : "border-gray-200 bg-gray-50"}`}>
                      <p className={`text-xs uppercase tracking-[0.12em] ${isDarkMode ? "text-gray-500" : "text-gray-500"}`}>Шаг 1</p>
                      <p className={`mt-2 text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>Файлы и параметры получены</p>
                    </div>
                    <div className={`rounded-2xl border p-4 ${isDarkMode ? "border-[#7A8B4A]/30 bg-[#7A8B4A]/8" : "border-[#7A8B4A]/20 bg-[#7A8B4A]/5"}`}>
                      <p className="text-xs uppercase tracking-[0.12em] text-[#7A8B4A]">Шаг 2</p>
                      <p className={`mt-2 text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                        {resolvedMode === "furniture" ? "Ищем похожие товары" : "Генерируем результат"}
                      </p>
                    </div>
                    <div className={`rounded-2xl border p-4 ${isDarkMode ? "border-gray-800 bg-gray-900" : "border-gray-200 bg-gray-50"}`}>
                      <p className={`text-xs uppercase tracking-[0.12em] ${isDarkMode ? "text-gray-500" : "text-gray-500"}`}>Шаг 3</p>
                      <p className={`mt-2 text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>Покажем готовый результат</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {effectiveStatus === "failed" && (
            <div className={`rounded-2xl p-6 text-center sm:p-12 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
              <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-red-100 flex items-center justify-center">
                <XCircle className="w-8 h-8 text-red-600" />
              </div>
              <h3 className={`text-xl font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Не удалось обработать запрос</h3>
              <p className={`text-sm mb-8 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                {errorMessage || "Возможно, проблема с загруженным изображением или временные технические неполадки."}
              </p>

              <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                <Button onClick={handleRepeat} className="bg-[#7A8B4A] hover:bg-[#6a7a3f] text-white">
                  <RotateCw className="w-4 h-4 mr-2" />
                  Попробовать снова
                </Button>
                <Button
                  onClick={handleBack}
                  variant="outline"
                  className={isDarkMode ? "border-gray-700 text-gray-300 hover:bg-gray-800" : "border-gray-300 text-gray-700 hover:bg-gray-50"}
                >
                  Изменить параметры
                </Button>
              </div>

              <div className={`rounded-xl p-6 ${isDarkMode ? "bg-gray-900 border border-gray-800" : "bg-gray-50 border border-gray-200"}`}>
                <div className="flex items-start gap-3 text-left">
                  <HelpCircle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`} />
                  <div>
                    <h4 className={`font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Нужна помощь?</h4>
                    <p className={`text-sm mb-3 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                      Если проблема повторяется, свяжитесь с поддержкой:
                    </p>
                    <div className="flex flex-col gap-2 text-sm">
                      <a href="mailto:owner@vizuai.example" className="text-[#7A8B4A] hover:underline">owner@vizuai.example</a>
                      <a href="https://example.com/support" className="text-[#7A8B4A] hover:underline">Telegram: [support handle removed]</a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {effectiveStatus === "completed" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="space-y-6">
                {resolvedMode === "furniture" && furnitureResult?.final_image_url && (
                  <div className={`rounded-2xl p-5 sm:p-6 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
                    <h2 className={`text-lg font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Найденные предметы</h2>
                    <div className="space-y-3">
                      <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                        Размеченное изображение
                      </label>
                      <div className="rounded-xl overflow-hidden border border-gray-700">
                        <ZoomableImageCard
                          src={furnitureResult.final_image_url}
                          alt="Размеченное изображение"
                          label="Размеченное изображение"
                          className="h-40 w-full object-cover sm:h-48"
                          fallbackClassName="flex h-40 w-full items-center justify-center bg-gray-100 text-center text-gray-500 sm:h-48"
                          onOpen={() => openViewer("result")}
                        />
                      </div>
                      <p className={`text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                        Показаны объекты, по которым выполнен поиск мебели.
                      </p>
                    </div>
                  </div>
                )}

                <div className={`rounded-2xl p-5 sm:p-6 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
                  <h2 className={`text-lg font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Вводные данные</h2>

                  {inputImage && (
                    <div className="space-y-3 mb-4">
                      <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                        {resolvedMode === "furniture" ? "Фото мебели" : "Фото помещения"}
                      </label>
                      <div className="rounded-xl overflow-hidden border border-gray-700">
                        <ZoomableImageCard
                          src={inputImage}
                          alt="Input"
                          label={resolvedMode === "furniture" ? "Фото мебели" : "Фото помещения"}
                          className="h-40 w-full object-cover sm:h-48"
                          fallbackClassName="flex h-40 w-full items-center justify-center bg-gray-100 text-center text-gray-500 sm:h-48"
                          onOpen={() => openViewer("input")}
                        />
                      </div>
                    </div>
                  )}

                  {referenceImage && (
                    <div className="space-y-3 mb-4">
                      <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>Референс</label>
                      <div className="rounded-xl overflow-hidden border border-gray-700">
                        <ZoomableImageCard
                          src={referenceImage}
                          alt="Reference"
                          label="Референс"
                          className="h-40 w-full object-cover sm:h-48"
                          fallbackClassName="flex h-40 w-full items-center justify-center bg-gray-100 text-center text-gray-500 sm:h-48"
                          onOpen={() => openViewer("reference")}
                        />
                      </div>
                    </div>
                  )}

                  {prompt && (
                    <div className="space-y-3">
                      <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>Описание</label>
                      <div className={`p-4 rounded-xl border text-sm ${
                        isDarkMode ? "bg-gray-900 border-gray-700 text-gray-300" : "bg-gray-50 border-gray-200 text-gray-700"
                      }`}>
                        {prompt}
                      </div>
                    </div>
                  )}
                </div>

                <div className={`rounded-2xl p-5 sm:p-6 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
                  <h3 className={`text-lg font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Информация</h3>
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <Clock className={`w-4 h-4 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`} />
                      <div>
                        <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-600"}`}>Статус</p>
                        <p className={`text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                          {resolvedMode === "furniture" ? "Поиск завершен" : "Результат готов"}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Zap className={`w-4 h-4 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`} />
                      <div>
                        <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-600"}`}>Использовано запросов</p>
                        <p className={`text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>{unitsSpent || 1}</p>
                      </div>
                    </div>
                    {metadataTime && (
                      <div className="flex items-center gap-3">
                        <CheckCircle className={`w-4 h-4 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`} />
                        <div>
                          <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-600"}`}>Завершено</p>
                          <p className={`text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                            {new Date(metadataTime).toLocaleTimeString("ru-RU")}
                          </p>
                        </div>
                      </div>
                    )}
                    <div className="flex items-center gap-3">
                      <Clock className={`w-4 h-4 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`} />
                      <div>
                        <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-600"}`}>Хранение</p>
                        <p className={`text-sm font-medium ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                          Изображения доступны 30 дней
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className={`rounded-2xl p-5 sm:p-6 ${isDarkMode ? "bg-[#7A8B4A]/10 border border-[#7A8B4A]/20" : "bg-[#7A8B4A]/5 border border-[#7A8B4A]/20"}`}>
                  <div className="flex items-start gap-3">
                    <HelpCircle className="w-5 h-5 text-[#7A8B4A] flex-shrink-0" />
                    <div>
                      <h4 className={`font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Не нравится результат?</h4>
                      <p className={`text-sm mb-3 ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                        Попробуйте изменить описание или загрузить другое фото. Если нужно, можно сразу повторить запуск.
                      </p>
                      <p className={`text-sm mb-3 ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                        Важные результаты лучше скачать заранее
                      </p>
                      <div className="flex flex-col gap-1 text-sm">
                        <a href="mailto:owner@vizuai.example" className="text-[#7A8B4A] hover:underline">owner@vizuai.example</a>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-2 space-y-6">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <h2 className={`text-lg font-semibold ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                    {resolvedMode === "furniture" ? "Найденная мебель" : "Результат"}
                  </h2>
                  {resolvedMode !== "furniture" && resultImage && (
                    <Button
                      onClick={handleDownload}
                      variant="outline"
                      className={`w-full sm:w-auto ${isDarkMode ? "border-gray-700 text-gray-300 hover:bg-gray-800" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`}
                    >
                      <Download className="w-4 h-4 mr-2" />
                      Скачать
                    </Button>
                  )}
                </div>

                {resolvedMode !== "furniture" && resultImage && (
                  <div className="space-y-6">
                    <div className="rounded-2xl overflow-hidden border border-gray-700">
                      <ZoomableImageCard
                        src={resultImage}
                        alt="Result"
                        label="Результат"
                        className="w-full"
                        fallbackClassName="flex min-h-[20rem] w-full items-center justify-center bg-gray-100 text-center text-gray-500"
                        onOpen={() => openViewer("result")}
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                      <Button onClick={handleRepeat} variant="outline" className={isDarkMode ? "border-gray-700 text-gray-300 hover:bg-gray-800" : "border-gray-300 text-gray-700 hover:bg-gray-50"}>
                        <RotateCw className="w-4 h-4 mr-2" />
                        Повторить
                      </Button>
                      <Button onClick={handleEdit} variant="outline" className={isDarkMode ? "border-gray-700 text-gray-300 hover:bg-gray-800" : "border-gray-300 text-gray-700 hover:bg-gray-50"}>
                        <Edit className="w-4 h-4 mr-2" />
                        Редактировать
                      </Button>
                      <Button onClick={handleSearchFurniture} className="bg-[#7A8B4A] hover:bg-[#6a7a3f] text-white">
                        <Search className="w-4 h-4 mr-2" />
                        Найти мебель
                      </Button>
                    </div>
                  </div>
                )}

                {resolvedMode === "furniture" && (
                  <>
                    {!furnitureResult?.object_cards || furnitureResult.object_cards.length === 0 ? (
                      <div className={`rounded-2xl p-12 text-center ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
                        <div className={`w-16 h-16 rounded-full mx-auto mb-6 flex items-center justify-center ${isDarkMode ? "bg-gray-800" : "bg-gray-100"}`}>
                          <PackageX className={`w-8 h-8 ${isDarkMode ? "text-gray-600" : "text-gray-400"}`} />
                        </div>
                        <h3 className={`text-xl font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Ничего не найдено</h3>
                        <p className={`text-sm mb-6 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                          К сожалению, мы не смогли найти похожую мебель на маркетплейсах. Попробуйте загрузить другое фото.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4 justify-center">
                          <Button onClick={handleRepeat} className="bg-[#7A8B4A] hover:bg-[#6a7a3f] text-white">
                            <RotateCw className="w-4 h-4 mr-2" />
                            Попробовать снова
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-6">
                        <div className="space-y-4">
                          {furnitureResult.object_cards.map((objectCard, index) => {
                            const normalizedCard = normalizeFurnitureCard(objectCard as Record<string, unknown>, index);
                            const title = normalizedCard.title;
                            const products = normalizedCard.products;
                            return (
                              <div
                                key={`${title}-${index}`}
                                className={`rounded-2xl p-5 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}
                              >
                                <h3 className={`text-lg font-semibold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}>{title}</h3>
                                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                                  {products.length === 0 && (
                                    <div className={`rounded-xl p-4 text-sm lg:col-span-2 ${isDarkMode ? "bg-gray-900 text-gray-400" : "bg-gray-50 text-gray-600"}`}>
                                      Для этого объекта ссылки не найдены.
                                    </div>
                                  )}
                                  {products.map((product, productIndex: number) => (
                                    <div
                                      key={`${product.url || product.title || productIndex}`}
                                      className={`rounded-xl p-4 ${isDarkMode ? "bg-gray-900" : "bg-gray-50"}`}
                                    >
                                      <div className="flex items-start gap-3">
                                        {product.image_url && (
                                          <AppImage
                                            src={product.image_url}
                                            alt={product.title || title}
                                            className="h-20 w-20 rounded-lg object-cover flex-shrink-0"
                                            fallbackClassName="flex h-20 w-20 items-center justify-center rounded-lg bg-gray-100 text-center text-gray-500"
                                          />
                                        )}
                                        <div className="min-w-0 flex-1">
                                          <p className={`font-medium mb-1 line-clamp-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>{product.title || title}</p>
                                          {product.price && <p className="text-[#7A8B4A] font-semibold mb-1">{product.price}</p>}
                                          {product.marketplace && product.marketplace !== product.title && (
                                            <p className={`text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>{product.marketplace}</p>
                                          )}
                                          {product.url && (
                                            <a
                                              href={product.url}
                                              target="_blank"
                                              rel="noopener noreferrer"
                                              className="inline-flex items-center gap-1 mt-2 text-sm text-[#7A8B4A] hover:underline"
                                            >
                                              Открыть
                                              <ExternalLink className="w-3.5 h-3.5" />
                                            </a>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                          <Button onClick={handleRepeat} variant="outline" className={isDarkMode ? "border-gray-700 text-gray-300 hover:bg-gray-800" : "border-gray-300 text-gray-700 hover:bg-gray-50"}>
                            <RotateCw className="w-4 h-4 mr-2" />
                            Повторить
                          </Button>
                          <Button onClick={handleBack} className="bg-[#7A8B4A] hover:bg-[#6a7a3f] text-white">
                            <Search className="w-4 h-4 mr-2" />
                            Новый поиск
                          </Button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <ResultImageViewer
        open={viewerOpen}
        onOpenChange={setViewerOpen}
        images={viewerImages}
        activeImageId={activeViewerImageId}
        onActiveImageChange={setActiveViewerImageId}
        prompt={prompt}
        onDownload={resultImage ? handleDownload : undefined}
      />
    </div>
  );
}
