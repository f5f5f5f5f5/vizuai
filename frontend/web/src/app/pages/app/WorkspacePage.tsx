import { useCallback, useEffect, useMemo, useState } from "react";
import { Sparkles, Image, Search, Upload, X, Wand2, Loader2, CreditCard, AlertCircle, RotateCw, CircleHelp } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { AppImage } from "@/app/components/AppImage";
import { useTheme } from "@/app/contexts/ThemeContext";
import { useSearchParams, useNavigate, useLocation } from "react-router";
import { useAuth } from "@/app/contexts/AuthContext";
import { api, ApiError } from "@/app/lib/api";
import { clearBillingResume, loadBillingResume, saveBillingResume, type BillingResumeContext } from "@/app/lib/billingResume";
import { trackAppClick } from "@/app/lib/analytics/client";

type WorkMode = null | "design" | "reference" | "furniture";
type LaunchStage =
  | "idle"
  | "restoring_reuse"
  | "preparing"
  | "uploading_source"
  | "uploading_reference"
  | "creating_draft"
  | "starting_job";

type WorkspaceErrorKind =
  | "reuse"
  | "source_upload"
  | "reference_upload"
  | "launch"
  | "validation";

type WorkspaceErrorState = {
  kind: WorkspaceErrorKind;
  title: string;
  message: string;
};

async function readFilePreview(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(reader.error || new Error("FILE_PREVIEW_FAILED"));
    reader.readAsDataURL(file);
  });
}

export function WorkspacePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const selectedMode = (searchParams.get("mode") as WorkMode) || null;
  const { isDarkMode } = useTheme();
  const { balance } = useAuth();

  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [uploadedImageFile, setUploadedImageFile] = useState<File | null>(null);
  const [uploadedImageFileId, setUploadedImageFileId] = useState<string | null>(null);

  const [uploadedReference, setUploadedReference] = useState<string | null>(null);
  const [uploadedReferenceFile, setUploadedReferenceFile] = useState<File | null>(null);
  const [uploadedReferenceFileId, setUploadedReferenceFileId] = useState<string | null>(null);

  const [prompt, setPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [launchStage, setLaunchStage] = useState<LaunchStage>("idle");
  const [errorState, setErrorState] = useState<WorkspaceErrorState | null>(null);
  const [resumeContext, setResumeContext] = useState<BillingResumeContext | null>(() => loadBillingResume());
  const [isResumeLoading, setIsResumeLoading] = useState(false);

  const currentBalance = balance;
  const preloadedPrompt = location.state?.preloadedPrompt;
  const reuseResultId = location.state?.reuseResultId as string | undefined;
  const editResultId = location.state?.editResultId as string | undefined;
  const furnitureSeedResultId = location.state?.furnitureSeedResultId as string | undefined;

  const loadReuse = useCallback(async () => {
    if (!selectedMode) {
      return;
    }

    setErrorState(null);
    setLaunchStage(reuseResultId || editResultId || furnitureSeedResultId ? "restoring_reuse" : "idle");

    if (reuseResultId || editResultId || furnitureSeedResultId) {
      try {
        const payload =
          selectedMode === "furniture"
            ? furnitureSeedResultId
              ? await api.getDesignFurnitureSeed(furnitureSeedResultId)
              : await api.getFurnitureReuse(reuseResultId as string)
            : editResultId
              ? await api.getDesignEditSeed(editResultId)
              : await api.getDesignReuse(reuseResultId as string);
        setUploadedImage(payload.source_image_url);
        setUploadedImageFile(null);
        setUploadedImageFileId(payload.source_file_id);
        setPrompt(payload.user_request || "");
        if (selectedMode === "reference") {
          setUploadedReference(payload.style_reference_image_url || null);
          setUploadedReferenceFile(null);
          setUploadedReferenceFileId(payload.style_reference_file_id || null);
        } else {
          setUploadedReference(null);
          setUploadedReferenceFile(null);
          setUploadedReferenceFileId(null);
        }
        setLaunchStage("idle");
        return;
      } catch (error) {
        console.error("Failed to load reuse payload:", error);
        setErrorState({
          kind: "reuse",
          title: "Не удалось восстановить прошлый запуск",
          message: "Мы не смогли подтянуть исходные файлы и параметры из предыдущего результата. Можно попробовать ещё раз или начать заново.",
        });
        setLaunchStage("idle");
      }
    }

    setUploadedImage(null);
    setUploadedImageFile(null);
    setUploadedImageFileId(null);
    setPrompt(preloadedPrompt || "");
    setUploadedReference(null);
    setUploadedReferenceFile(null);
    setUploadedReferenceFileId(null);
    setLaunchStage("idle");
  }, [editResultId, furnitureSeedResultId, preloadedPrompt, reuseResultId, selectedMode]);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      await loadReuse();
      if (cancelled) {
        return;
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [loadReuse]);

  useEffect(() => {
    setResumeContext(loadBillingResume());
  }, [selectedMode, location.state]);

  const modes = useMemo(
    () => [
      {
        id: "design" as const,
        title: "Дизайн интерьера",
        description: "Загрузите фото помещения и опишите желаемый стиль",
        icon: Sparkles,
        color: "from-purple-500 to-pink-500",
        cost: 1,
      },
      {
        id: "reference" as const,
        title: "Дизайн по референсу",
        description: "Создайте дизайн на основе понравившегося изображения",
        icon: Image,
        color: "from-blue-500 to-cyan-500",
        cost: 1,
      },
      {
        id: "furniture" as const,
        title: "Поиск мебели",
        description: "Найдите похожую мебель на маркетплейсах",
        icon: Search,
        color: "from-orange-500 to-yellow-500",
        cost: 1,
      },
    ],
    [],
  );

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>, type: "main" | "reference") => {
    const file = e.target.files?.[0];
    if (!file) return;

    let previewUrl = "";
    try {
      previewUrl = await readFilePreview(file);
    } catch (error) {
      console.error("Failed to build local image preview:", error);
      previewUrl = URL.createObjectURL(file);
    }

    if (type === "main") {
      setUploadedImage(previewUrl);
      setUploadedImageFile(file);
      setUploadedImageFileId(null);
    } else {
      setUploadedReference(previewUrl);
      setUploadedReferenceFile(file);
      setUploadedReferenceFileId(null);
    }
    setErrorState(null);
  };

  const clearMainImage = () => {
    setUploadedImage(null);
    setUploadedImageFile(null);
    setUploadedImageFileId(null);
    setErrorState((current) => (current?.kind === "source_upload" ? null : current));
  };

  const clearReferenceImage = () => {
    setUploadedReference(null);
    setUploadedReferenceFile(null);
    setUploadedReferenceFileId(null);
    setErrorState((current) => (current?.kind === "reference_upload" ? null : current));
  };

  const uploadFileToStorage = async (
    file: File,
    purpose: string,
    kind: "image" | "style-reference",
  ) => {
    try {
      const intent =
        kind === "style-reference"
          ? await api.createStyleReferenceUploadIntent({
              filename: file.name,
              content_type: file.type || "image/jpeg",
              size_bytes: file.size,
              purpose,
            })
          : await api.createImageUploadIntent({
              filename: file.name,
              content_type: file.type || "image/jpeg",
              size_bytes: file.size,
              purpose,
            });

      await api.putSignedUpload(intent.upload.upload_url, file, intent.upload.headers);
      const completed = await api.completeUpload(intent.upload.upload_id, intent.upload.storage_key);
      return completed.file.file_id;
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "UPLOAD_NETWORK_ERROR") {
          throw new Error(kind === "style-reference" ? "REFERENCE_UPLOAD_NETWORK_ERROR" : "SOURCE_UPLOAD_NETWORK_ERROR");
        }
        if (error.code === "UPLOAD_PUT_FAILED") {
          throw new Error(kind === "style-reference" ? "REFERENCE_UPLOAD_PUT_FAILED" : "SOURCE_UPLOAD_PUT_FAILED");
        }
      }
      throw error;
    }
  };

  const ensureMainFileId = async () => {
    if (uploadedImageFileId) {
      return uploadedImageFileId;
    }

    if (uploadedImageFile) {
      const fileId = await uploadFileToStorage(
        uploadedImageFile,
        selectedMode === "furniture" ? "furniture-source" : "design-source",
        "image",
      );
      setUploadedImageFileId(fileId);
      return fileId;
    }

    throw new Error("SOURCE_IMAGE_REQUIRED");
  };

  const ensureReferenceFileId = async () => {
    if (uploadedReferenceFileId) {
      return uploadedReferenceFileId;
    }

    if (uploadedReferenceFile) {
      const fileId = await uploadFileToStorage(uploadedReferenceFile, "design-style-reference", "style-reference");
      setUploadedReferenceFileId(fileId);
      return fileId;
    }

    return null;
  };

  const handleGenerate = async () => {
    if (!selectedMode) {
      return;
    }

    if (!uploadedImage && !uploadedImageFileId && !uploadedImageFile) {
      setErrorState({
        kind: "validation",
        title: "Нужно загрузить исходное изображение",
        message: "Сначала добавьте фото, с которым будем работать.",
      });
      return;
    }

    if (selectedMode === "design" && !prompt.trim()) {
      setErrorState({
        kind: "validation",
        title: "Не хватает описания",
        message: "Добавьте короткое описание желаемого результата, чтобы мы понимали, что именно нужно сгенерировать.",
      });
      return;
    }

    if (selectedMode === "reference" && !uploadedReference && !uploadedReferenceFileId && !uploadedReferenceFile) {
      setErrorState({
        kind: "validation",
        title: "Не хватает референса",
        message: "Для этого сценария нужно загрузить изображение-образец, на стиль которого будем ориентироваться.",
      });
      return;
    }

    setIsGenerating(true);
    setErrorState(null);
    setLaunchStage("preparing");

    let pendingDraftId: string | null = null;

    try {
      setLaunchStage("uploading_source");
      const sourceFileId = await ensureMainFileId();

      if (selectedMode === "furniture") {
        setLaunchStage("creating_draft");
        void trackAppClick("workspace", "generate_click", { mode: selectedMode });
        const draft = await api.createFurnitureDraft({
          source_file_id: sourceFileId,
          user_request: null,
        });
        pendingDraftId = draft.id;
        if (!hasEnoughBalance) {
          saveBillingResume({
            draftId: draft.id,
            mode: selectedMode,
          });
          navigate("/app/billing", {
            state: {
              resumeDraftId: draft.id,
              resumeMode: selectedMode,
            },
          });
          return;
        }
        setLaunchStage("starting_job");
        const job = await api.createFurnitureJob(draft.id);
        clearBillingResume();
        navigate(`/app/workspace/result/${job.id}`, {
          state: {
            jobId: job.id,
            mode: selectedMode,
            inputImage: uploadedImage,
          },
        });
        return;
      }

      if (selectedMode === "reference") {
        setLaunchStage("uploading_reference");
      }
      const styleReferenceFileId = selectedMode === "reference" ? await ensureReferenceFileId() : null;
      setLaunchStage("creating_draft");
      void trackAppClick("workspace", "generate_click", { mode: selectedMode });
      const draft = await api.createDesignDraft({
        source_file_id: sourceFileId,
        user_request: prompt.trim(),
        style_reference_enabled: selectedMode === "reference",
        style_reference_file_id: styleReferenceFileId,
      });
      pendingDraftId = draft.id;
      if (!hasEnoughBalance) {
        saveBillingResume({
          draftId: draft.id,
          mode: selectedMode,
        });
        navigate("/app/billing", {
          state: {
            resumeDraftId: draft.id,
            resumeMode: selectedMode,
          },
        });
        return;
      }
      setLaunchStage("starting_job");
      const job = await api.createDesignJob(draft.id);
      clearBillingResume();
      navigate(`/app/workspace/result/${job.id}`, {
        state: {
          jobId: job.id,
          mode: selectedMode,
          inputImage: uploadedImage,
          referenceImage: uploadedReference,
          prompt,
        },
      });
    } catch (error) {
      console.error("Failed to start workspace flow:", error);
      if (error instanceof ApiError) {
        if (error.status === 402) {
          if (pendingDraftId) {
            saveBillingResume({
              draftId: pendingDraftId,
              mode: selectedMode,
            });
            navigate("/app/billing", {
              state: {
                resumeDraftId: pendingDraftId,
                resumeMode: selectedMode,
              },
            });
            return;
          }
          navigate("/app/billing");
          return;
        }
        setErrorState({
          kind: "launch",
          title: "Не удалось запустить сценарий",
          message: error.message,
        });
      } else if (error instanceof Error) {
        if (error.message === "SOURCE_UPLOAD_NETWORK_ERROR") {
          setErrorState({
            kind: "source_upload",
            title: "Не удалось загрузить исходное фото",
            message: "Похоже, соединение прервалось во время загрузки. Попробуйте ещё раз или выберите файл заново.",
          });
        } else if (error.message === "SOURCE_UPLOAD_PUT_FAILED") {
          setErrorState({
            kind: "source_upload",
            title: "Исходное фото не загрузилось",
            message: "Файл не удалось отправить в хранилище. Попробуйте загрузить изображение ещё раз.",
          });
        } else if (error.message === "REFERENCE_UPLOAD_NETWORK_ERROR") {
          setErrorState({
            kind: "reference_upload",
            title: "Не удалось загрузить референс",
            message: "Во время загрузки изображения-образца пропало соединение. Попробуйте повторить ещё раз.",
          });
        } else if (error.message === "REFERENCE_UPLOAD_PUT_FAILED") {
          setErrorState({
            kind: "reference_upload",
            title: "Референс не загрузился",
            message: "Не получилось отправить изображение-референс в хранилище. Выберите файл заново и повторите запуск.",
          });
        } else {
          setErrorState({
            kind: "launch",
            title: "Не удалось запустить сценарий",
            message: "Попробуйте ещё раз. Если проблема повторится, можно обновить страницу или обратиться в поддержку.",
          });
        }
      } else {
        setErrorState({
          kind: "launch",
          title: "Не удалось запустить сценарий",
          message: "Попробуйте ещё раз. Если проблема повторится, можно обновить страницу или обратиться в поддержку.",
        });
      }
    } finally {
      setIsGenerating(false);
      setLaunchStage("idle");
    }
  };

  const handleResumeSavedRequest = async () => {
    if (!resumeContext || isResumeLoading) {
      return;
    }

    if (currentBalance < 1) {
      navigate("/app/billing", {
        state: {
          resumeDraftId: resumeContext.draftId,
          resumeMode: resumeContext.mode,
        },
      });
      return;
    }

    setIsResumeLoading(true);
    setErrorState(null);
    void trackAppClick("workspace", "resume_saved_request_click", {
      mode: resumeContext.mode,
    });

    try {
      const draft =
        resumeContext.mode === "furniture"
          ? await api.getFurnitureDraft(resumeContext.draftId)
          : await api.getDesignDraft(resumeContext.draftId);
      const job =
        resumeContext.mode === "furniture"
          ? await api.createFurnitureJob(resumeContext.draftId)
          : await api.createDesignJob(resumeContext.draftId);

      clearBillingResume();
      setResumeContext(null);

      navigate(`/app/workspace/result/${job.id}`, {
        state: {
          jobId: job.id,
          mode: resumeContext.mode,
          inputImage: draft.source_image_url,
          referenceImage:
            resumeContext.mode === "reference" && "style_reference_image_url" in draft
              ? draft.style_reference_image_url || undefined
              : undefined,
          prompt: draft.user_request || undefined,
        },
      });
    } catch (error) {
      console.error("Failed to resume saved request:", error);
      if (error instanceof ApiError) {
        setErrorState({
          kind: "launch",
          title: "Не удалось запустить сохраненный запрос",
          message: error.message,
        });
      } else {
        setErrorState({
          kind: "launch",
          title: "Не удалось запустить сохраненный запрос",
          message: "Попробуйте ещё раз. Если проблема повторится, можно обновить страницу или обратиться в поддержку.",
        });
      }
    } finally {
      setIsResumeLoading(false);
    }
  };

  const resetWorkspace = () => {
    setUploadedImage(null);
    setUploadedImageFile(null);
    setUploadedImageFileId(null);
    setUploadedReference(null);
    setUploadedReferenceFile(null);
    setUploadedReferenceFileId(null);
    setPrompt("");
    setErrorState(null);
    setIsGenerating(false);
    setLaunchStage("idle");
    navigate("/app/workspace");
  };

  if (!selectedMode) {
    return (
      <div className="mx-auto max-w-7xl p-4 sm:p-8">
        <div className="space-y-8">
          <div>
            <h1 className={`mb-2 text-2xl font-bold sm:text-3xl ${isDarkMode ? "text-white" : "text-gray-900"}`}>Студия дизайна</h1>
            <p className={isDarkMode ? "text-gray-300" : "text-gray-600"}>Выберите способ работы</p>
          </div>

          {errorState && (
            <div className={`rounded-xl p-4 ${isDarkMode ? "bg-red-900/20 border border-red-800 text-red-200" : "bg-red-50 border border-red-200 text-red-700"}`}>
              <div className="flex items-start gap-3">
                <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
                <div>
                  <p className="mb-1 text-sm font-semibold">{errorState.title}</p>
                  <p className="text-sm">{errorState.message}</p>
                </div>
              </div>
            </div>
          )}

          {resumeContext && (
            <div className={`rounded-xl p-5 sm:p-6 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className={`mb-2 text-xl font-semibold ${isDarkMode ? "text-white" : "text-gray-900"}`}>Ваш запрос сохранён</h2>
                  <p className={`text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                    {currentBalance >= 1
                      ? "Теперь можно запустить сохраненный сценарий"
                      : "Можно запустить его после пополнения баланса"}
                  </p>
                </div>
                <Button
                  type="button"
                  disabled={isResumeLoading}
                  onClick={handleResumeSavedRequest}
                  className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F] disabled:opacity-60"
                >
                  {isResumeLoading
                    ? "Запускаем..."
                    : currentBalance >= 1
                      ? "Запустить сохраненный запрос"
                      : "Перейти к оплате"}
                </Button>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {modes.map((mode) => (
              <button
                key={mode.id}
                onClick={() => {
                  void trackAppClick("workspace", "mode_select", { mode: mode.id });
                  navigate(`/app/workspace?mode=${mode.id}`);
                }}
                className={`group relative rounded-2xl p-6 text-left transition-all duration-300 hover:scale-[1.02] hover:border-[#7A8B4A] sm:p-8 ${
                  isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"
                }`}
              >
                <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${mode.color} opacity-10 rounded-full blur-3xl group-hover:opacity-20 transition-opacity`} />

                <div className="relative">
                  <div className="mb-6 w-fit rounded-xl bg-[#7A8B4A]/20 p-4">
                    <mode.icon className="w-8 h-8 text-[#7A8B4A]" />
                  </div>

                  <h3 className={`text-xl font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>{mode.title}</h3>
                  <p className={`text-sm mb-6 ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>{mode.description}</p>

                  <div className="flex items-center justify-between">
                    <span className="text-[#7A8B4A] font-semibold">1 запрос</span>
                    <span className={`text-sm group-hover:text-[#7A8B4A] transition-colors ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                      Выбрать →
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div className="bg-[#7A8B4A]/10 border border-[#7A8B4A]/20 rounded-xl p-6">
            <h4 className={`font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>💡 Совет</h4>
            <p className={`text-sm ${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
              Для лучших результатов используйте качественные фотографии с хорошим освещением. Опишите стиль максимально детально.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const currentMode = modes.find((m) => m.id === selectedMode);
  const hasEnoughBalance = currentBalance >= (currentMode?.cost || 0);
  const guidePath =
    selectedMode === "design"
      ? "/how-to-design-by-photo"
      : selectedMode === "reference"
        ? "/how-to-design-by-reference"
        : selectedMode === "furniture"
          ? "/how-to-find-furniture-by-photo"
          : null;
  const launchStageMessage =
    launchStage === "restoring_reuse"
      ? "Восстанавливаем прошлый запуск..."
      : launchStage === "preparing"
        ? "Подготавливаем запуск..."
        : launchStage === "uploading_source"
          ? "Загружаем исходное изображение..."
          : launchStage === "uploading_reference"
            ? "Загружаем изображение-референс..."
            : launchStage === "creating_draft"
              ? "Сохраняем параметры..."
              : launchStage === "starting_job"
                ? "Запускаем сценарий..."
                : null;

  return (
    <div className="h-full flex flex-col">
      <div className={`border-b px-4 sm:px-8 py-6 ${isDarkMode ? "border-gray-800" : "border-gray-200"}`}>
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6 w-full sm:w-auto">
            <div>
              <h1 className={`text-xl sm:text-2xl font-bold mb-1 ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                {currentMode?.title}
              </h1>
              <p className={`text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                {currentMode?.description}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3 sm:pl-6 sm:border-l border-gray-700">
              <div className={`px-3 sm:px-4 py-2 rounded-lg ${isDarkMode ? "bg-gray-800" : "bg-gray-100"}`}>
                <div className="flex items-center gap-2">
                  <CreditCard className="w-4 h-4 text-[#7A8B4A]" />
                  <span className={`text-xs sm:text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>Баланс:</span>
                  <span className="text-xs sm:text-sm font-bold text-[#7A8B4A]">{currentBalance}</span>
                </div>
              </div>
              <div className={`px-3 sm:px-4 py-2 rounded-lg ${isDarkMode ? "bg-[#7A8B4A]/20" : "bg-[#7A8B4A]/10"}`}>
                <span className={`text-xs sm:text-sm ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>Стоимость: </span>
                <span className="text-xs sm:text-sm font-bold text-[#7A8B4A]">1 запрос</span>
              </div>
              {guidePath && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    void trackAppClick("workspace", "guide_open", { mode: selectedMode });
                    window.open(guidePath, "_blank", "noopener,noreferrer");
                  }}
                  className={`h-10 ${isDarkMode ? "border-gray-700 bg-gray-900 text-gray-200 hover:bg-gray-800 hover:text-white" : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"}`}
                >
                  <CircleHelp className="h-4 w-4" />
                  Инструкция
                </Button>
              )}
            </div>
          </div>

          <Button
            variant="outline"
            onClick={resetWorkspace}
            className={`${isDarkMode ? "border-gray-700 bg-gray-900 text-gray-200 hover:bg-gray-800 hover:text-white" : "border-gray-300 text-gray-700 hover:bg-gray-50"} w-full sm:w-auto`}
          >
            Назад
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto p-4 sm:p-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 sm:gap-8">
            <div className="space-y-6">
              <div className="space-y-4">
                <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                  {selectedMode === "reference" ? "Фото помещения" : selectedMode === "furniture" ? "Фото мебели" : "Загрузите фото"}
                </label>

                {!uploadedImage ? (
                  <label className={`relative block cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors sm:p-12 ${
                    isDarkMode ? "border-gray-700 hover:border-gray-600 bg-[#0F0F0F]" : "border-gray-300 hover:border-gray-400 bg-gray-50"
                  }`}>
                    <input type="file" accept="image/*" onChange={(e) => handleImageUpload(e, "main")} className="hidden" />
                    <Upload className={`mx-auto mb-4 h-10 w-10 sm:h-12 sm:w-12 ${isDarkMode ? "text-gray-600" : "text-gray-400"}`} />
                    <p className={`text-sm font-medium mb-1 ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>Нажмите для загрузки</p>
                    <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-500"}`}>PNG, JPG до 10MB</p>
                  </label>
                ) : (
                  <div className="relative rounded-xl overflow-hidden">
                    <AppImage src={uploadedImage} alt="Uploaded" className="h-64 w-full object-cover" />
                    <button
                      onClick={clearMainImage}
                      className="absolute top-2 right-2 p-2 bg-black/50 hover:bg-black/70 rounded-lg text-white transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>

              {selectedMode === "reference" && (
                <div className="space-y-4">
                  <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>Референс дизайна</label>

                  {!uploadedReference ? (
                    <label className={`relative block cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors sm:p-12 ${
                      isDarkMode ? "border-gray-700 hover:border-gray-600 bg-[#0F0F0F]" : "border-gray-300 hover:border-gray-400 bg-gray-50"
                    }`}>
                      <input type="file" accept="image/*" onChange={(e) => handleImageUpload(e, "reference")} className="hidden" />
                      <Upload className={`mx-auto mb-4 h-10 w-10 sm:h-12 sm:w-12 ${isDarkMode ? "text-gray-600" : "text-gray-400"}`} />
                      <p className={`text-sm font-medium mb-1 ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>Загрузите референс</p>
                      <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-500"}`}>PNG, JPG до 10MB</p>
                    </label>
                  ) : (
                    <div className="relative rounded-xl overflow-hidden">
                      <AppImage src={uploadedReference} alt="Reference" className="h-64 w-full object-cover" />
                      <button
                        onClick={clearReferenceImage}
                        className="absolute top-2 right-2 p-2 bg-black/50 hover:bg-black/70 rounded-lg text-white transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              )}

              {selectedMode !== "furniture" && (
                <div className="space-y-4">
                  <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                    {selectedMode === "reference" ? "Дополнительные пожелания (опционально)" : "Опишите желаемый стиль"}
                  </label>
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder={
                      selectedMode === "reference"
                        ? "Например: добавить больше растений, изменить цвет стен на светло-серый..."
                        : "Например: современный скандинавский стиль, светлые тона, минимализм..."
                    }
                    rows={4}
                    className={`w-full px-4 py-3 rounded-xl border resize-none focus:outline-none focus:ring-2 focus:ring-[#7A8B4A] ${
                      isDarkMode ? "bg-[#0F0F0F] border-gray-700 text-white placeholder-gray-500" : "bg-white border-gray-300 text-gray-900 placeholder-gray-400"
                    }`}
                  />
                </div>
              )}

              {errorState && (
                <div className={`rounded-xl p-4 ${isDarkMode ? "bg-red-900/20 border border-red-800 text-red-200" : "bg-red-50 border border-red-200 text-red-700"}`}>
                  <div className="flex items-start gap-3">
                    <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="mb-1 text-sm font-semibold">{errorState.title}</p>
                      <p className="text-sm">{errorState.message}</p>
                      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                        {errorState.kind === "reuse" && (
                          <>
                            <Button
                              type="button"
                              size="sm"
                              onClick={() => void loadReuse()}
                              className="bg-[#7A8B4A] text-white hover:bg-[#6a7a3f]"
                            >
                              <RotateCw className="mr-2 h-4 w-4" />
                              Попробовать снова
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={resetWorkspace}
                              className={isDarkMode ? "border-red-700 text-red-200 hover:bg-red-950/30" : "border-red-200 text-red-700 hover:bg-red-100"}
                            >
                              Начать заново
                            </Button>
                          </>
                        )}
                        {(errorState.kind === "source_upload" || errorState.kind === "reference_upload" || errorState.kind === "launch") && (
                          <Button
                            type="button"
                            size="sm"
                            onClick={() => void handleGenerate()}
                            className="bg-[#7A8B4A] text-white hover:bg-[#6a7a3f]"
                          >
                            <RotateCw className="mr-2 h-4 w-4" />
                            Повторить
                          </Button>
                        )}
                        {errorState.kind === "source_upload" && (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={clearMainImage}
                            className={isDarkMode ? "border-red-700 text-red-200 hover:bg-red-950/30" : "border-red-200 text-red-700 hover:bg-red-100"}
                          >
                            Выбрать фото заново
                          </Button>
                        )}
                        {errorState.kind === "reference_upload" && (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={clearReferenceImage}
                            className={isDarkMode ? "border-red-700 text-red-200 hover:bg-red-950/30" : "border-red-200 text-red-700 hover:bg-red-100"}
                          >
                            Выбрать референс заново
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {!hasEnoughBalance && (
                <div className={`rounded-xl p-4 mb-4 ${isDarkMode ? "bg-[#7A8B4A]/12 border border-[#7A8B4A]/30" : "bg-[#7A8B4A]/10 border border-[#7A8B4A]/20"}`}>
                  <div className="flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-[#7A8B4A] flex-shrink-0 mt-0.5" />
                    <div>
                      <p className={`text-sm font-medium mb-1 ${isDarkMode ? "text-white" : "text-gray-900"}`}>Сначала подготовьте запрос</p>
                      <p className={`text-xs ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                        Для запуска понадобится 1 запрос. После оплаты вы сможете сразу продолжить.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <Button
                onClick={() => void handleGenerate()}
                disabled={!uploadedImage || isGenerating || (selectedMode === "reference" && !uploadedReference)}
                className="w-full bg-[#7A8B4A] hover:bg-[#6a7a3f] text-white h-12 text-base font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    {hasEnoughBalance ? "Генерация..." : "Сохраняем..."}
                  </>
                ) : (
                  <>
                    <Wand2 className="w-5 h-5 mr-2" />
                    {hasEnoughBalance ? "Сгенерировать (1 запрос)" : "Сохранить и перейти к оплате"}
                  </>
                )}
              </Button>
            </div>

            <div className="space-y-4">
              <label className={`block text-sm font-medium ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                {selectedMode === "furniture" ? "Результаты поиска" : "Результат"}
              </label>

              <div className={`flex min-h-[320px] items-center justify-center rounded-xl border-2 border-dashed p-6 sm:min-h-[480px] lg:min-h-[600px] ${
                isDarkMode ? "border-gray-700 bg-[#0F0F0F]" : "border-gray-300 bg-gray-50"
              }`}>
                {isGenerating ? (
                  <div className="text-center">
                    <Loader2 className={`w-12 h-12 mx-auto mb-4 animate-spin ${isDarkMode ? "text-gray-600" : "text-gray-400"}`} />
                    <p className={`text-sm font-medium mb-1 ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                      {selectedMode === "furniture" ? "Готовим поиск мебели" : "Готовим результат"}
                    </p>
                    <p className={`text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                      {launchStageMessage || (selectedMode === "furniture" ? "Ищем похожую мебель..." : "Создаем дизайн...")}
                    </p>
                  </div>
                ) : (
                  <div className="text-center">
                    {currentMode && <currentMode.icon className={`w-12 h-12 mx-auto mb-4 ${isDarkMode ? "text-gray-600" : "text-gray-400"}`} />}
                    <p className={`text-sm font-medium mb-1 ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
                      {selectedMode === "furniture" ? "Результаты появятся после обработки" : "Результат появится после генерации"}
                    </p>
                    <p className={`text-xs ${isDarkMode ? "text-gray-500" : "text-gray-500"}`}>
                      После запуска вы перейдете на отдельный экран результата
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
