import { Image, ShoppingBag, Palette } from "lucide-react";
import { useLocale } from "@/app/i18n";

export function Features() {
  const { isEnglish } = useLocale();
  const features = [
    {
      icon: Image,
      title: isEnglish ? "Design from photo" : "Дизайн по фото",
      description: isEnglish ? "Upload a room photo and describe the style you want" : "Загрузите фото комнаты и опишите желаемый стиль",
    },
    {
      icon: Palette,
      title: isEnglish ? "Design by reference" : "Дизайн по референсу",
      description: isEnglish ? "Use an inspiration image as the visual reference" : "Используйте понравившееся изображение как образец",
    },
    {
      icon: ShoppingBag,
      title: isEnglish ? "Furniture search" : "Поиск мебели",
      description: isEnglish ? "Find similar furniture and open marketplace links faster" : "Найдём похожую мебель и подберём ссылки на маркетплейсах",
    },
  ];

  return (
    <section className="bg-white px-6 py-20 sm:py-24">
      <div className="max-w-6xl mx-auto">
        <div className="grid gap-10 md:grid-cols-3 md:gap-12">
          {features.map((feature, index) => (
            <div key={index} className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[#7A8B4A] text-white mb-6 shadow-lg">
                <feature.icon className="w-8 h-8" />
              </div>
              <h3 className="text-xl mb-3 text-[#2C3419]">{feature.title}</h3>
              <p className="text-[#5A6B3A]">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
