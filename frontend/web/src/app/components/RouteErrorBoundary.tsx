import { AlertCircle, ArrowLeft, Home, RotateCw } from "lucide-react";
import { isRouteErrorResponse, useNavigate, useRouteError } from "react-router";
import { Button } from "@/app/components/ui/button";

function getErrorMessage(error: unknown) {
  if (isRouteErrorResponse(error)) {
    if (error.status === 404) {
      return "Такой страницы нет или она была перемещена";
    }
    return "Не удалось открыть страницу";
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "Произошла ошибка при загрузке страницы";
}

export function RouteErrorBoundary() {
  const navigate = useNavigate();
  const error = useRouteError();
  const message = getErrorMessage(error);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F5F3E7] px-6 py-16">
      <div className="w-full max-w-xl rounded-[28px] border border-[#E3DFC8] bg-white p-8 text-center shadow-[0_18px_48px_rgba(36,42,20,0.08)] sm:p-10">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-[#F3EED9] text-[#7A8B4A]">
          <AlertCircle className="h-8 w-8" />
        </div>
        <h1 className="mb-3 text-3xl text-[#2C3419] sm:text-4xl">Не удалось открыть страницу</h1>
        <p className="mx-auto mb-8 max-w-lg text-base leading-7 text-[#5A6B3A]">
          {message}
        </p>
        <div className="flex flex-col justify-center gap-3 sm:flex-row">
          <Button
            onClick={() => window.location.reload()}
            className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
          >
            <RotateCw className="mr-2 h-4 w-4" />
            Обновить страницу
          </Button>
          <Button
            variant="outline"
            onClick={() => navigate("/")}
            className="border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            <Home className="mr-2 h-4 w-4" />
            На главную
          </Button>
          <Button
            variant="outline"
            onClick={() => navigate(-1)}
            className="border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Назад
          </Button>
        </div>
      </div>
    </div>
  );
}
