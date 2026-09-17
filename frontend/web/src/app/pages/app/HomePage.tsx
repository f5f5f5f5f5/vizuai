import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "@/app/components/ui/button";
import { CreditCard, Clock, Sparkles, Image, Search, RotateCw, FileX, AlertCircle } from "lucide-react";
import { useTheme } from "@/app/contexts/ThemeContext";
import { useAuth } from "@/app/contexts/AuthContext";
import { useLocale } from "@/app/i18n";
import { api, type HistoryItem } from "@/app/lib/api";
import { parseApiDate } from "@/app/lib/apiDate";
import { toUiJobStatus } from "@/app/lib/jobStatus";
import { formatRequestLabel, requestWord } from "@/app/lib/requestLabel";
import { trackAppClick } from "@/app/lib/analytics/client";

export function HomePage() {
  const navigate = useNavigate();
  const { isDarkMode } = useTheme();
  const { balance } = useAuth();
  const { isEnglish, locale } = useLocale();
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setIsLoading(true);
    setHistoryError(null);
    try {
      const history = await api.getHistory(1, 8);
      setHistoryItems(history.items || []);
    } catch (error) {
      console.error("Failed to load dashboard:", error);
      setHistoryItems([]);
      setHistoryError(isEnglish ? "Could not load request history. Try again a bit later." : "Не удалось загрузить историю запросов. Попробуйте обновить страницу чуть позже.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      await loadHistory();
      if (cancelled) {
        return;
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [loadHistory]);

  const lastRequest = useMemo(() => {
    if (!historyItems.length) {
      return null;
    }
    return parseApiDate(historyItems[0].created_at);
  }, [historyItems]);

  const formatDate = (date: Date) => {
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) {
      return isEnglish ? `${diffMins} min ago` : `${diffMins} мин назад`;
    } else if (diffHours < 24) {
      return isEnglish ? `${diffHours} h ago` : `${diffHours} ч назад`;
    } else if (diffDays === 1) {
      return isEnglish ? "Yesterday" : "Вчера";
    } else {
      return date.toLocaleDateString(isEnglish ? "en-US" : "ru-RU", { day: 'numeric', month: 'long' });
    }
  };

  const getTypeIcon = (mode: string) => {
    switch (mode) {
      case "design":
        return <Sparkles className="w-4 h-4" />;
      case "reference":
        return <Image className="w-4 h-4" />;
      case "furniture_search":
        return <Search className="w-4 h-4" />;
      default:
        return <Sparkles className="w-4 h-4" />;
    }
  };

  const getModeLabel = (mode: string) => {
    if (mode === "reference") return isEnglish ? "Design by reference" : "Дизайн по референсу";
    if (mode === "furniture_search") return isEnglish ? "Furniture search" : "Поиск мебели";
    return isEnglish ? "Interior design" : "Дизайн интерьера";
  };

  const quickStartModes = [
    {
      id: "design",
      title: isEnglish ? "Interior design" : "Дизайн интерьера",
      description: isEnglish ? "Upload a room photo and describe the style you want" : "Загрузите фото помещения и опишите желаемый стиль",
      icon: Sparkles,
    },
    {
      id: "reference",
      title: isEnglish ? "Design by reference" : "Дизайн по референсу",
      description: isEnglish ? "Create a redesign from an inspiration image" : "Создайте дизайн на основе понравившегося изображения",
      icon: Image,
    },
    {
      id: "furniture",
      title: isEnglish ? "Furniture search" : "Поиск мебели",
      description: isEnglish ? "Find similar furniture on marketplaces" : "Найдите похожую мебель на маркетплейсах",
      icon: Search,
    },
  ] as const;

  const getUiStatusLabel = (status: string) => {
    const uiStatus = toUiJobStatus(status);
    if (uiStatus === "completed") return isEnglish ? "Completed" : "Завершено";
    if (uiStatus === "failed") return isEnglish ? "Failed" : "Ошибка";
    return isEnglish ? "In progress" : "В работе";
  };

  const getUiStatusClassName = (status: string) => {
    const uiStatus = toUiJobStatus(status);
    if (uiStatus === "completed") return "text-green-600";
    if (uiStatus === "failed") return "text-red-600";
    return "text-[#7A8B4A]";
  };

  const handleRetry = (item: HistoryItem, e: React.MouseEvent) => {
    e.stopPropagation();
    void trackAppClick("home", "history_retry_click", { mode: item.mode, result_id: item.id });
    const mode = item.mode === "furniture_search" ? "furniture" : item.mode;
    navigate(`/app/workspace?mode=${mode}`, {
      state: { reuseResultId: item.id },
    });
  };

  const openResult = (item: HistoryItem) => {
    void trackAppClick("home", "history_open_result", { mode: item.mode, result_id: item.id });
    navigate(`/app/workspace/result/${item.id}`);
  };

  const isNewUser = !isLoading && !historyError && historyItems.length === 0;

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6 sm:space-y-8">
      {/* Welcome Section */}
      <div>
        <h1 className={`text-2xl sm:text-3xl font-bold mb-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Welcome to VizuAI" : "Добро пожаловать в VizuAI"}</h1>
        <p className={isDarkMode ? 'text-gray-300' : 'text-gray-600'}>{isEnglish ? "Create interior concepts with AI" : "Создавайте дизайны интерьеров с помощью искусственного интеллекта"}</p>
      </div>

      {/* Balance & Quick Actions */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-3">
        {/* Balance Card */}
        <div className="rounded-2xl bg-gradient-to-br from-[#7A8B4A] to-[#6B7B3F] p-5 text-white sm:p-6 md:col-span-2">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <p className="text-white/80 text-sm mb-1">{isEnglish ? "Your balance" : "Ваш баланс"}</p>
              <p className="text-3xl font-bold sm:text-4xl">{formatRequestLabel(balance, locale)}</p>
            </div>
            <div className="bg-white/20 p-3 rounded-xl">
              <CreditCard className="w-6 h-6" />
            </div>
          </div>
          <Button 
            onClick={() => {
              void trackAppClick("home", "balance_topup_click");
              navigate('/app/billing');
            }}
            className="bg-white text-[#7A8B4A] hover:bg-white/90 w-full"
          >
            {isEnglish ? "Top up balance" : "Пополнить баланс"}
          </Button>
        </div>

        {/* Last Request Card */}
        <div className={`rounded-2xl p-6 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
          <div className="flex items-start gap-3 mb-4">
            <div className="bg-[#7A8B4A]/20 p-3 rounded-xl">
              <Clock className="w-5 h-5 text-[#7A8B4A]" />
            </div>
            <div>
              <p className={`text-sm mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Last request" : "Последний запрос"}</p>
              <p className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{lastRequest ? formatDate(lastRequest) : isEnglish ? "No requests yet" : "Еще не было"}</p>
            </div>
          </div>
          <Button 
            onClick={() => {
              void trackAppClick("home", "last_request_create_new");
              navigate('/app/workspace');
            }}
            variant="outline"
            className={`w-full ${isDarkMode ? 'border-gray-700 bg-gray-900 text-gray-200 hover:bg-gray-800 hover:text-white' : 'border-gray-300 text-gray-700 hover:bg-gray-50'}`}
          >
            {isEnglish ? "Create new" : "Создать новый"}
          </Button>
        </div>
      </div>

      {isNewUser && (
        <div>
          <div className="mb-4">
            <h2 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Where to start" : "С чего начать"}</h2>
            <p className={`mt-1 text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Choose a scenario" : "Выберите сценарий работы"}</p>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {quickStartModes.map((mode) => (
              <button
                key={mode.id}
                onClick={() => {
                  void trackAppClick("home", "new_user_mode_select", { mode: mode.id });
                  navigate(`/app/workspace?mode=${mode.id}`);
                }}
                className={`rounded-2xl border p-6 text-left transition-all duration-300 hover:scale-[1.01] hover:border-[#7A8B4A] ${
                  isDarkMode ? 'bg-[#0F0F0F] border-gray-800' : 'bg-white border-gray-200'
                }`}
              >
                <div className="mb-4 inline-flex rounded-2xl bg-[#7A8B4A]/15 p-3 text-[#7A8B4A]">
                  <mode.icon className="h-6 w-6" />
                </div>
                <h3 className={`mb-2 text-lg font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{mode.title}</h3>
                <p className={`mb-4 text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{mode.description}</p>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-[#7A8B4A]">{formatRequestLabel(1, locale)}</span>
                  <span className={`text-sm ${isDarkMode ? 'text-gray-500' : 'text-gray-500'}`}>{isEnglish ? "Choose →" : "Выбрать →"}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* History Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Request history" : "История запросов"}</h2>
          <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{historyError ? "—" : formatRequestLabel(historyItems.length, locale)}</span>
        </div>
        <p className={`mb-4 text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
          {isEnglish ? "History and images are available for 30 days" : "История и изображения доступны 30 дней"}
        </p>

        {!isLoading && historyError ? (
          <div className={`rounded-2xl p-6 text-center sm:p-12 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
            <div className={`w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center ${isDarkMode ? 'bg-gray-800' : 'bg-gray-100'}`}>
              <AlertCircle className={`w-8 h-8 ${isDarkMode ? 'text-gray-500' : 'text-gray-500'}`} />
            </div>
            <h3 className={`text-lg font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
              {isEnglish ? "History is temporarily unavailable" : "История временно недоступна"}
            </h3>
            <p className={`mb-6 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
              {historyError}
            </p>
            <Button
              onClick={() => void loadHistory()}
              className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
            >
              {isEnglish ? "Try again" : "Попробовать снова"}
            </Button>
          </div>
        ) : !isLoading && historyItems.length === 0 ? (
          // Empty State
          <div className={`rounded-2xl p-6 text-center sm:p-12 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
            <div className={`w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center ${isDarkMode ? 'bg-gray-800' : 'bg-gray-100'}`}>
              <FileX className={`w-8 h-8 ${isDarkMode ? 'text-gray-600' : 'text-gray-400'}`} />
            </div>
            <h3 className={`text-lg font-semibold mb-2 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
              {isEnglish ? "History is empty" : "История пока пуста"}
            </h3>
            <p className={`mb-6 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
              {isNewUser ? (isEnglish ? "After the first run, your results will appear here." : "После первого запуска здесь появятся ваши результаты.") : isEnglish ? "You have not created any results yet." : "Вы еще не создали ни одного дизайна"}
            </p>
            {!isNewUser && (
              <Button
                onClick={() => {
                  void trackAppClick("home", "empty_history_create_first");
                  navigate('/app/workspace');
                }}
                className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
              >
                {isEnglish ? "Create first design" : "Создать первый дизайн"}
              </Button>
            )}
          </div>
        ) : (
          <div className={`rounded-2xl overflow-hidden ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
            <div className={`divide-y ${isDarkMode ? 'divide-gray-800' : 'divide-gray-200'}`}>
              {(isLoading ? Array.from({ length: 3 }) : historyItems).map((item, index) => (
                <div 
                  key={isLoading ? `skeleton-${index}` : item.id}
                  className={`p-6 transition-colors ${!isLoading ? "cursor-pointer" : ""} ${isDarkMode ? 'hover:bg-gray-900/50' : 'hover:bg-gray-50'}`}
                  onClick={!isLoading ? () => openResult(item as HistoryItem) : undefined}
                >
                  {isLoading ? (
                    <div className="animate-pulse flex items-start justify-between gap-4">
                      <div className="flex items-start gap-4 flex-1">
                        <div className={`w-10 h-10 rounded-xl ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
                        <div className="flex-1 space-y-2">
                          <div className={`w-32 h-5 rounded ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
                          <div className={`w-64 h-4 rounded ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
                          <div className={`w-24 h-4 rounded ${isDarkMode ? "bg-gray-800" : "bg-gray-200"}`} />
                        </div>
                      </div>
                    </div>
                  ) : (
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex items-start gap-4 flex-1">
                      <div className="bg-[#7A8B4A]/20 p-3 rounded-xl text-[#7A8B4A]">
                        {getTypeIcon(item.mode)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium text-[#7A8B4A] bg-[#7A8B4A]/20 px-2 py-1 rounded">
                            {getModeLabel(item.mode)}
                          </span>
                        </div>
                        <p className={`font-medium mb-1 truncate ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{item.user_request || item.title || (isEnglish ? "No description" : "Без описания")}</p>
                        <p className={`text-sm ${isDarkMode ? 'text-gray-500' : 'text-gray-600'}`}>{formatDate(parseApiDate(item.created_at))}</p>
                      </div>
                    </div>
                    <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
                      <div className="text-right">
                        <p className={`font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>-{item.units_spent || 1} {requestWord(item.units_spent || 1, locale)}</p>
                        <p className={`text-xs ${getUiStatusClassName(item.status)}`}>
                          {getUiStatusLabel(item.status)}
                        </p>
                      </div>
                      {item.retry_eligible && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => handleRetry(item, e)}
                          className={`flex items-center gap-2 ${isDarkMode ? 'border-gray-700 bg-gray-900 text-gray-200 hover:bg-gray-800 hover:text-white' : 'border-gray-300 text-gray-700 hover:bg-gray-50'}`}
                        >
                          <RotateCw className="w-3.5 h-3.5" />
                          {isEnglish ? "Repeat" : "Повторить"}
                        </Button>
                      )}
                    </div>
                  </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Quick Start */}
      {!isNewUser && (
        <div className={`rounded-2xl border border-[#7A8B4A]/20 bg-gradient-to-r from-[#7A8B4A]/10 to-[#C69C6D]/10 p-6 text-center sm:p-8 ${isDarkMode ? '' : 'bg-opacity-50'}`}>
          <h3 className={`mb-2 text-xl font-semibold sm:text-2xl ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Ready to create a new design?" : "Готовы создать новый дизайн?"}</h3>
          <p className={`mb-6 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Choose one of the three workflows in the studio" : "Выберите один из трёх способов работы в студии"}</p>
          <Button 
            onClick={() => navigate('/app/workspace')}
            size="lg"
            className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
          >
            {isEnglish ? "Open studio" : "Перейти в студию"}
          </Button>
        </div>
      )}
    </div>
  );
}
