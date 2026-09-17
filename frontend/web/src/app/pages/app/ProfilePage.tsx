import { User, Mail, Calendar, TrendingUp, CreditCard, LogOut, FileText, Loader2, AlertCircle, RotateCw } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { useTheme } from "@/app/contexts/ThemeContext";
import { useAuth } from "@/app/contexts/AuthContext";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { useLocale } from "@/app/i18n";
import { api, type BillingPayment } from "@/app/lib/api";
import { parseApiDate } from "@/app/lib/apiDate";
import { Input } from "@/app/components/ui/input";
import { formatRequestLabel } from "@/app/lib/requestLabel";

export function ProfilePage() {
  const { isDarkMode } = useTheme();
  const { user, logout, balance, refreshSession } = useAuth();
  const { isEnglish, locale, publicPath, setLocale } = useLocale();
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [profileForm, setProfileForm] = useState({
    display_name: "",
    locale: "",
    timezone: "",
  });
  const [usage, setUsage] = useState({
    total_runs: 0,
    completed_runs: 0,
    failed_runs: 0,
    design_runs: 0,
    furniture_runs: 0,
    credits_spent: 0,
  });
  const [paymentHistory, setPaymentHistory] = useState<BillingPayment[]>([]);
  const [isProfileDataLoading, setIsProfileDataLoading] = useState(true);
  const [profileLoadError, setProfileLoadError] = useState<string | null>(null);

  const loadProfileData = useCallback(async () => {
    setIsProfileDataLoading(true);
    setProfileLoadError(null);
    try {
      const [usageResponse, payments] = await Promise.all([api.getAccountUsage(), api.getPayments()]);
      setUsage(usageResponse.usage);
      setPaymentHistory(payments);
    } catch (error) {
      console.error("Failed to load profile:", error);
      setUsage({
        total_runs: 0,
        completed_runs: 0,
        failed_runs: 0,
        design_runs: 0,
        furniture_runs: 0,
        credits_spent: 0,
      });
      setPaymentHistory([]);
      setProfileLoadError(isEnglish ? "Could not load usage stats and payment history. Try refreshing again." : "Не удалось загрузить статистику и историю оплат. Попробуйте обновить данные ещё раз.");
    } finally {
      setIsProfileDataLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProfileData();
  }, [loadProfileData]);

  useEffect(() => {
    setProfileForm({
      display_name: user?.display_name || "",
      locale: user?.locale || "ru",
      timezone: user?.timezone || "Europe/Moscow",
    });
  }, [user]);

  const userData = useMemo(
    () => ({
      email: user?.email || "—",
      name: user?.display_name || (isEnglish ? "VizuAI user" : "Пользователь VizuAI"),
      joinDate: user?.created_at
        ? parseApiDate(user.created_at).toLocaleDateString(isEnglish ? "en-US" : "ru-RU", { day: "numeric", month: "long", year: "numeric" })
        : "—",
      totalRequests: usage.total_runs,
      tokensSpent: usage.credits_spent,
      currentBalance: balance,
    }),
    [user, usage, balance],
  );

  const usageStats = useMemo(
    () => [
      { label: isEnglish ? "Interior design" : "Дизайн интерьера", count: usage.design_runs, tokens: usage.design_runs },
      { label: isEnglish ? "Design by reference" : "Дизайн по референсу", count: Math.max(usage.completed_runs - usage.design_runs - usage.furniture_runs, 0), tokens: Math.max(usage.completed_runs - usage.design_runs - usage.furniture_runs, 0) },
      { label: isEnglish ? "Furniture search" : "Поиск мебели", count: usage.furniture_runs, tokens: usage.furniture_runs },
    ],
    [isEnglish, usage],
  );

  const totalRequestsSafe = Math.max(userData.totalRequests, 1);

  const handleSaveProfile = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      await api.updateAccount({
        display_name: profileForm.display_name.trim() || null,
        locale: profileForm.locale.trim() || null,
        timezone: profileForm.timezone.trim() || null,
      });
      await refreshSession();
      setIsEditing(false);
      setSaveMessage(isEnglish ? "Profile updated." : "Профиль обновлен.");
    } catch (error) {
      console.error("Failed to update profile:", error);
      setSaveMessage(isEnglish ? "Could not save changes." : "Не удалось сохранить изменения.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleLanguageChange = async (nextLocale: "ru" | "en") => {
    if (nextLocale === (user?.locale || "ru") || isSaving) {
      return;
    }
    setIsSaving(true);
    setSaveMessage(null);
    try {
      await api.updateAccount({ locale: nextLocale });
      setLocale(nextLocale);
      setProfileForm((current) => ({ ...current, locale: nextLocale }));
      await refreshSession();
      setSaveMessage(nextLocale === "en" ? "Interface language updated" : "Язык интерфейса обновлен");
    } catch (error) {
      console.error("Failed to update interface language:", error);
      setSaveMessage(isEnglish ? "Could not update interface language" : "Не удалось обновить язык интерфейса");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:space-y-8 sm:p-6 lg:p-8">
      {/* Header */}
      <div>
        <h1 className={`mb-2 text-2xl font-bold sm:text-3xl ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Profile" : "Профиль"}</h1>
        <p className={isDarkMode ? 'text-gray-300' : 'text-gray-600'}>{isEnglish ? "Account and settings management" : "Управление аккаунтом и настройками"}</p>
      </div>

      {/* Profile Card */}
      <div className={`rounded-2xl p-5 sm:p-8 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
        <div className="mb-8 flex flex-col items-start gap-5 sm:flex-row sm:gap-6">
          {/* Avatar */}
          <div className="rounded-2xl bg-gradient-to-br from-[#7A8B4A] to-[#6B7B3F] p-5 text-white sm:p-8">
            <User className="h-12 w-12 sm:h-16 sm:w-16" />
          </div>

          {/* Info */}
          <div className="flex-1">
            <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className={`mb-2 text-xl font-bold sm:text-2xl ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                  {userData.name}
                </h2>
                <div className="flex flex-col gap-2 text-sm sm:flex-row sm:items-center sm:gap-4">
                  <div className={`flex items-center gap-2 break-all ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                    <Mail className="w-4 h-4" />
                    {userData.email}
                  </div>
                  <div className={`flex items-center gap-2 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                    <Calendar className="w-4 h-4" />
                    {isEnglish ? `Since ${userData.joinDate}` : `С ${userData.joinDate}`}
                  </div>
                </div>
              </div>
              <Button
                onClick={() => {
                  if (isEditing) {
                    void handleSaveProfile();
                    return;
                  }
                  setSaveMessage(null);
                  setIsEditing(true);
                }}
                variant="outline"
                className={`w-full sm:w-auto ${isDarkMode ? 'border-gray-700 bg-gray-900 text-gray-200 hover:bg-gray-800 hover:text-white' : ''}`}
              >
                {isSaving ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {isEnglish ? "Saving" : "Сохраняем"}
                  </>
                ) : isEditing ? (isEnglish ? 'Save' : 'Сохранить') : isEnglish ? 'Edit profile' : 'Редактировать профиль'}
              </Button>
            </div>

            {saveMessage && (
              <div className={`mb-4 rounded-xl px-4 py-3 text-sm ${saveMessage.includes("Не удалось") || saveMessage.includes("Could not") ? "bg-red-50 text-red-700 border border-red-200" : "bg-[#7A8B4A]/10 text-[#5A6B3A] border border-[#7A8B4A]/20"}`}>
                {saveMessage}
              </div>
            )}

            {isEditing && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>{isEnglish ? "Name" : "Имя"}</label>
                  <Input
                    value={profileForm.display_name}
                    onChange={(event) => setProfileForm((current) => ({ ...current, display_name: event.target.value }))}
                    className={isDarkMode ? "bg-gray-900 border-gray-700 text-white" : ""}
                    placeholder={isEnglish ? "How we should address you" : "Как к вам обращаться"}
                  />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>{isEnglish ? "Language" : "Язык"}</label>
                  <Input
                    value={profileForm.locale}
                    onChange={(event) => setProfileForm((current) => ({ ...current, locale: event.target.value }))}
                    className={isDarkMode ? "bg-gray-900 border-gray-700 text-white" : ""}
                    placeholder="ru"
                  />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-2 ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>{isEnglish ? "Time zone" : "Часовой пояс"}</label>
                  <Input
                    value={profileForm.timezone}
                    onChange={(event) => setProfileForm((current) => ({ ...current, timezone: event.target.value }))}
                    className={isDarkMode ? "bg-gray-900 border-gray-700 text-white" : ""}
                    placeholder="Europe/Moscow"
                  />
                </div>
              </div>
            )}

            {/* Stats */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className={`rounded-xl p-4 ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
                <p className={`text-sm mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Total requests" : "Всего запросов"}</p>
                <p className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{userData.totalRequests}</p>
              </div>
              <div className={`rounded-xl p-4 ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
                <p className={`text-sm mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Spent requests" : "Потрачено запросов"}</p>
                <p className={`text-2xl font-bold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{userData.tokensSpent}</p>
              </div>
              <div className={`rounded-xl p-4 ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
                <p className={`text-sm mb-1 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Balance" : "Баланс"}</p>
                <p className={`text-2xl font-bold text-[#7A8B4A]`}>{userData.currentBalance}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {profileLoadError && (
        <div className={`rounded-2xl p-5 sm:p-6 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className={`mt-0.5 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${isDarkMode ? "bg-gray-800" : "bg-gray-100"}`}>
                <AlertCircle className={`h-5 w-5 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`} />
              </div>
              <div>
                <h3 className={`mb-1 font-semibold ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                  {isEnglish ? "Profile data is temporarily unavailable" : "Данные профиля временно недоступны"}
                </h3>
                <p className={`text-sm ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                  {profileLoadError}
                </p>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => void loadProfileData()}
              disabled={isProfileDataLoading}
              className={isDarkMode ? "border-gray-700 bg-gray-900 text-gray-200 hover:bg-gray-800 hover:text-white" : "border-gray-300 text-gray-700 hover:bg-gray-50"}
            >
              <RotateCw className={`mr-2 h-4 w-4 ${isProfileDataLoading ? "animate-spin" : ""}`} />
              {isEnglish ? "Refresh" : "Обновить"}
            </Button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-8">
        {/* Usage Statistics */}
        <div className={`rounded-2xl p-6 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
          <div className="flex items-center gap-3 mb-6">
            <div className="bg-[#7A8B4A]/20 p-3 rounded-xl">
              <TrendingUp className="w-5 h-5 text-[#7A8B4A]" />
            </div>
            <h3 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Usage statistics" : "Статистика использования"}</h3>
          </div>

          <div className="space-y-4">
            {usageStats.map((stat, index) => (
              <div key={index} className={`p-4 rounded-xl ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}>
                <div className="flex justify-between items-start mb-2">
                  <p className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{stat.label}</p>
                  <span className="text-sm text-[#7A8B4A] font-semibold">{formatRequestLabel(stat.count, locale)}</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className={`flex-1 h-2 rounded-full overflow-hidden ${isDarkMode ? 'bg-gray-800' : 'bg-gray-200'}`}>
                      <div 
                        className="h-full bg-[#7A8B4A] rounded-full"
                        style={{ width: `${userData.totalRequests > 0 ? (stat.count / totalRequestsSafe) * 100 : 0}%` }}
                      />
                    </div>
                    <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{formatRequestLabel(stat.tokens, locale)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Payment History */}
        <div className={`rounded-2xl p-6 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
          <div className="flex items-center gap-3 mb-6">
            <div className="bg-[#7A8B4A]/20 p-3 rounded-xl">
              <CreditCard className="w-5 h-5 text-[#7A8B4A]" />
            </div>
            <h3 className={`text-xl font-semibold ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Top-up history" : "История пополнений"}</h3>
          </div>

          <div className="space-y-3">
            {paymentHistory.length === 0 ? (
              <div className={`p-6 rounded-xl text-sm ${isDarkMode ? 'bg-gray-900 text-gray-400' : 'bg-gray-50 text-gray-600'}`}>
                {isEnglish ? "Payment history is empty." : "История оплат пока пуста."}
              </div>
            ) : (
              paymentHistory.map((payment) => (
                <div 
                  key={payment.id}
                  className={`p-4 rounded-xl ${isDarkMode ? 'bg-gray-900' : 'bg-gray-50'}`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <p className={`font-medium mb-1 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                        +{formatRequestLabel(payment.credits_amount, locale)}
                      </p>
                      <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{payment.provider || (isEnglish ? 'Payment' : 'Оплата')}</p>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                        {parseApiDate(payment.paid_at || payment.created_at).toLocaleDateString(isEnglish ? 'en-US' : 'ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}
                      </p>
                      <span className="text-xs text-[#7A8B4A] bg-[#7A8B4A]/10 px-2 py-1 rounded mt-1 inline-block">
                        {payment.price_final} ₽
                      </span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Settings */}
      <div className={`rounded-2xl p-6 ${isDarkMode ? 'bg-[#0F0F0F] border border-gray-800' : 'bg-white border border-gray-200'}`}>
        <h3 className={`text-xl font-semibold mb-6 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Account and documents" : "Аккаунт и документы"}</h3>
        
        <div className="space-y-4">
          <div className="py-4 border-b border-gray-200 dark:border-gray-800">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Interface language" : "Язык интерфейса"}</p>
                <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Choose the app language" : "Выберите язык приложения"}</p>
                <div className="mt-3 inline-flex rounded-xl border border-gray-200 p-1 dark:border-gray-700">
                  <button
                    type="button"
                    onClick={() => void handleLanguageChange("ru")}
                    disabled={isSaving}
                    className={`rounded-lg px-3 py-2 text-sm transition-colors ${
                      locale === "ru"
                        ? "bg-[#7A8B4A] text-white"
                        : isDarkMode
                          ? "text-gray-300 hover:bg-gray-800"
                          : "text-gray-700 hover:bg-gray-100"
                    }`}
                  >
                    Русский
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleLanguageChange("en")}
                    disabled={isSaving}
                    className={`rounded-lg px-3 py-2 text-sm transition-colors ${
                      locale === "en"
                        ? "bg-[#7A8B4A] text-white"
                        : isDarkMode
                          ? "text-gray-300 hover:bg-gray-800"
                          : "text-gray-700 hover:bg-gray-100"
                    }`}
                  >
                    English
                  </button>
                </div>
              </div>
              <div>
                <p className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>{isEnglish ? "Time zone" : "Часовой пояс"}</p>
                <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{user?.timezone || 'Europe/Moscow'}</p>
              </div>
            </div>
          </div>

          {/* Legal Documents */}
          <div className="py-4 border-b border-gray-200 dark:border-gray-800">
            <Link 
              to={publicPath("/legal")}
              className="flex items-center gap-3 group"
            >
              <FileText className={`w-5 h-5 ${isDarkMode ? 'text-gray-400 group-hover:text-gray-300' : 'text-gray-600 group-hover:text-gray-900'}`} />
              <div>
                <p className={`font-medium ${isDarkMode ? 'text-white group-hover:text-gray-100' : 'text-gray-900'}`}>{isEnglish ? "Legal documents" : "Юридические документы"}</p>
                <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`}>{isEnglish ? "Offer and privacy materials" : "Оферта, политика конфиденциальности"}</p>
              </div>
            </Link>
          </div>

          {/* Logout */}
          <div className="pt-4">
            <Button
              onClick={() => void logout()}
              variant="outline"
              className="w-full border-red-300 text-red-600 hover:bg-red-50 hover:border-red-400"
            >
              <LogOut className="w-4 h-4 mr-2" />
              {isEnglish ? "Sign out" : "Выйти из аккаунта"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
