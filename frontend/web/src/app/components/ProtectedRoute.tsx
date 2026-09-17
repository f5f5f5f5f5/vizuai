import { ReactNode, useEffect } from "react";
import { Link, useNavigate } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Loader2 } from "lucide-react";
import { Button } from "./ui/button";
import { useLocale } from "../i18n";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, authError, refreshSession } = useAuth();
  const { loginPath } = useLocale();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !authError) {
      navigate(loginPath, { replace: true });
    }
  }, [authError, isAuthenticated, isLoading, loginPath, navigate]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F5F3E7]">
        <div className="text-center">
          <Loader2 className="w-12 h-12 text-[#7A8B4A] animate-spin mx-auto mb-4" />
          <p className="text-gray-600">Загрузка...</p>
        </div>
      </div>
    );
  }

  if (authError && !isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#F5F3E7] flex items-center justify-center px-4">
        <div className="max-w-md rounded-2xl border border-gray-200 bg-white p-6 text-center shadow-lg sm:p-8">
          <h2 className="mb-3 text-xl font-semibold text-gray-900">Не удалось открыть приложение</h2>
          <p className="mb-6 text-sm text-gray-600">{authError}</p>
          <div className="flex flex-col gap-3">
            <Button
              onClick={() => void refreshSession()}
              className="w-full bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
            >
              Повторить
            </Button>
            <Button asChild variant="outline" className="w-full border-gray-300 text-gray-700 hover:bg-gray-50">
              <Link to="/">На главную</Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
