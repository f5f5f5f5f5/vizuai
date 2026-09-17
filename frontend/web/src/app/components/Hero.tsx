import { Sparkles } from "lucide-react";
import { Button } from "./ui/button";
import { useNavigate } from "react-router";
import { useLocale } from "@/app/i18n";
import { trackPublicClick } from "@/app/lib/analytics/client";
import heroBackground from "../../assets/hero/hero.jpg";

export function Hero() {
  const navigate = useNavigate();
  const { isEnglish, loginPath } = useLocale();

  return (
    <section className="relative flex min-h-[90vh] items-center justify-center overflow-hidden">
      {/* Background Image */}
      <div 
        className="absolute inset-0 bg-cover bg-center"
        style={{
          backgroundImage: `url('${heroBackground}')`
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/40 to-black/70" />
      </div>

      {/* Content */}
      <div className="relative z-10 mx-auto max-w-4xl px-4 text-center sm:px-6">
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-2 backdrop-blur-sm sm:px-4">
          <Sparkles className="w-4 h-4 text-white" />
          <span className="text-sm text-white">{isEnglish ? "AI interior design" : "Дизайн интерьера с помощью ИИ"}</span>
        </div>
        
        <h1 className="mb-6 text-4xl leading-tight text-white sm:text-5xl md:text-7xl">
          {isEnglish ? <>Turn any<br />space into your next idea</> : <>Превратите любое<br />пространство в мечту</>}
        </h1>
        
        <p className="mx-auto mb-10 max-w-2xl text-lg text-white/90 sm:text-xl md:text-2xl">
          {isEnglish ? "Upload a photo and get a polished interior concept in minutes" : "Загрузите фото — получите профессиональный дизайн за минуты"}
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Button 
            size="lg" 
            className="bg-[#7A8B4A] px-6 py-4 text-base text-white shadow-xl hover:bg-[#6B7B3F] sm:px-8 sm:py-6 sm:text-lg"
            onClick={() => {
              void trackPublicClick("landing", "hero_start_click");
              navigate(loginPath);
            }}
          >
            {isEnglish ? "Start creating" : "Начать создавать"}
          </Button>
          <Button 
            size="lg" 
            variant="outline" 
            className="border-white/30 bg-transparent px-6 py-4 text-base text-white hover:bg-white/10 hover:text-white sm:px-8 sm:py-6 sm:text-lg"
            onClick={() => {
              void trackPublicClick("landing", "hero_examples_click");
              document.getElementById('examples')?.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            {isEnglish ? "See examples" : "Посмотреть примеры"}
          </Button>
        </div>
      </div>
    </section>
  );
}
