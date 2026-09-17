import { ArrowLeft, Home, Sparkles } from "lucide-react";
import { useNavigate } from "react-router";
import { Button } from "@/app/components/ui/button";

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F5F3E7] flex items-center justify-center px-6">
      <div className="max-w-xl text-center">
        <div className="w-16 h-16 rounded-full bg-[#7A8B4A]/10 text-[#7A8B4A] flex items-center justify-center mx-auto mb-6">
          <Sparkles className="w-8 h-8" />
        </div>
        <h1 className="mb-4 text-3xl text-[#2C3419] sm:text-4xl">Страница не найдена</h1>
        <p className="text-[#5A6B3A] mb-8">
          Возможно, ссылка устарела или страница была перемещена. Вернитесь на главную или откройте приложение.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Button onClick={() => navigate("/")} className="bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]">
            <Home className="w-4 h-4 mr-2" />
            На главную
          </Button>
          <Button
            variant="outline"
            onClick={() => navigate(-1)}
            className="border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Назад
          </Button>
        </div>
      </div>
    </div>
  );
}
