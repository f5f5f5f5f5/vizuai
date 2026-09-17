import { Upload, Type, Image as ImageIcon, Sparkles, Tag, Search, Link2, ArrowRight } from "lucide-react";
import { Button } from "./ui/button";
import { useNavigate } from "react-router";
import { useLocale } from "@/app/i18n";

const designProcess = [
  {
    icon: Upload,
    title: "Загрузите фото",
    description: "Фото вашей комнаты"
  },
  {
    icon: Type,
    title: "Опишите стиль",
    description: "Текстовый запрос"
  },
  {
    icon: ImageIcon,
    title: "Референс",
    description: "Картинка-образец (опционально)"
  },
  {
    icon: Sparkles,
    title: "Получите рендер",
    description: "Готовый дизайн за минуты"
  }
];

const furnitureProcess = [
  {
    icon: Upload,
    title: "Загрузите фото",
    description: "Фото вашего интерьера"
  },
  {
    icon: Tag,
    title: "Разметка мебели",
    description: "ИИ определяет предметы"
  },
  {
    icon: Search,
    title: "Поиск на маркетплейсах",
    description: "Находим похожую мебель"
  },
  {
    icon: Link2,
    title: "Подборка ссылок",
    description: "Несколько вариантов по каждому предмету"
  }
];

type HowItWorksProps = {
  showHeading?: boolean;
  showCta?: boolean;
  sectionClassName?: string;
};

export function HowItWorks({
  showHeading = true,
  showCta = true,
  sectionClassName = "bg-white px-6 py-20 sm:py-24",
}: HowItWorksProps) {
  const navigate = useNavigate();
  const { isEnglish, loginPath } = useLocale();
  const designProcess = [
    {
      icon: Upload,
      title: isEnglish ? "Upload a photo" : "Загрузите фото",
      description: isEnglish ? "Your room photo" : "Фото вашей комнаты",
    },
    {
      icon: Type,
      title: isEnglish ? "Describe the style" : "Опишите стиль",
      description: isEnglish ? "Text request" : "Текстовый запрос",
    },
    {
      icon: ImageIcon,
      title: isEnglish ? "Reference" : "Референс",
      description: isEnglish ? "Optional inspiration image" : "Картинка-образец (опционально)",
    },
    {
      icon: Sparkles,
      title: isEnglish ? "Get the render" : "Получите рендер",
      description: isEnglish ? "Ready design in minutes" : "Готовый дизайн за минуты",
    },
  ];

  const furnitureProcess = [
    {
      icon: Upload,
      title: isEnglish ? "Upload a photo" : "Загрузите фото",
      description: isEnglish ? "Interior or object photo" : "Фото вашего интерьера",
    },
    {
      icon: Tag,
      title: isEnglish ? "Object markup" : "Разметка мебели",
      description: isEnglish ? "AI identifies the items" : "ИИ определяет предметы",
    },
    {
      icon: Search,
      title: isEnglish ? "Marketplace search" : "Поиск на маркетплейсах",
      description: isEnglish ? "We search for similar products" : "Находим похожую мебель",
    },
    {
      icon: Link2,
      title: isEnglish ? "Grouped links" : "Подборка ссылок",
      description: isEnglish ? "Several options per object" : "Несколько вариантов по каждому предмету",
    },
  ];

  return (
    <section className={sectionClassName}>
      <div className="max-w-7xl mx-auto">
        {showHeading ? (
          <div className="text-center mb-16">
            <h2 className="mb-4 text-3xl text-[#2C3419] sm:text-4xl md:text-5xl">
              {isEnglish ? "How it works" : "Как это работает?"}
            </h2>
          </div>
        ) : null}

        {/* Дизайн интерьера */}
        <div className="mb-20">
          <h3 className="mb-10 text-center text-2xl text-[#2C3419] md:text-3xl">
            {isEnglish ? "Interior design" : "Дизайн интерьера"}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 md:gap-4">
            {designProcess.map((step, index) => (
              <div key={index} className="relative">
                <div className="flex flex-col items-center text-center">
                  <div className="w-16 h-16 md:w-20 md:h-20 rounded-2xl bg-[#7A8B4A] text-white flex items-center justify-center mb-4 shadow-lg">
                    <step.icon className="w-8 h-8 md:w-10 md:h-10" />
                  </div>
                  <h4 className="text-lg md:text-xl mb-2 text-[#2C3419]">{step.title}</h4>
                  <p className="text-sm md:text-base text-[#5A6B3A]">{step.description}</p>
                </div>
                {index < designProcess.length - 1 && (
                  <div className="hidden md:flex absolute top-8 md:top-10 left-[calc(50%+2.5rem)] w-[calc(100%-5rem)] items-center justify-center">
                    <ArrowRight className="w-6 h-6 text-[#A4B374]" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Поиск мебели */}
        <div>
          <h3 className="mb-10 text-center text-2xl text-[#2C3419] md:text-3xl">
            {isEnglish ? "Furniture search" : "Поиск мебели"}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 md:gap-4">
            {furnitureProcess.map((step, index) => (
              <div key={index} className="relative">
                <div className="flex flex-col items-center text-center">
                  <div className="w-16 h-16 md:w-20 md:h-20 rounded-2xl bg-[#C69C6D] text-white flex items-center justify-center mb-4 shadow-lg">
                    <step.icon className="w-8 h-8 md:w-10 md:h-10" />
                  </div>
                  <h4 className="text-lg md:text-xl mb-2 text-[#2C3419]">{step.title}</h4>
                  <p className="text-sm md:text-base text-[#5A6B3A]">{step.description}</p>
                </div>
                {index < furnitureProcess.length - 1 && (
                  <div className="hidden md:flex absolute top-8 md:top-10 left-[calc(50%+2.5rem)] w-[calc(100%-5rem)] items-center justify-center">
                    <ArrowRight className="w-6 h-6 text-[#D4A574]" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* CTA Button */}
        {showCta ? (
          <div className="text-center mt-16">
            <Button 
              size="lg" 
              className="bg-[#7A8B4A] px-7 py-4 text-base text-white shadow-xl hover:bg-[#6B7B3F] sm:px-10 sm:py-6 sm:text-lg"
              onClick={() => navigate(loginPath)}
            >
              {isEnglish ? "Try it now" : "Попробовать сейчас"}
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
