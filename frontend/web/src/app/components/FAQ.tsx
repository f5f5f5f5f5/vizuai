import * as Accordion from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";
import { useLocale } from "@/app/i18n";

export function FAQ() {
  const { isEnglish } = useLocale();
  const faqs = [
    {
      question: isEnglish ? "How long does design generation take?" : "Сколько времени занимает создание дизайна?",
      answer: isEnglish
        ? "Most requests finish within a few minutes. Exact timing depends on the scenario, input image quality, and current load."
        : "Обычно запрос обрабатывается в течение нескольких минут. Точное время зависит от сценария, качества исходного изображения и текущей нагрузки.",
    },
    {
      question: isEnglish ? "How much does it cost?" : "Сколько стоят услуги?",
      answer: isEnglish
        ? "Every core scenario costs 1 request. Current packs, pricing, and promo codes are always shown on the billing page."
        : "Все основные сценарии стоят по 1 запросу. Актуальные пакеты, цены и промокоды всегда указаны на странице оплаты.",
    },
    {
      question: isEnglish ? "Can I try it for free?" : "Можно ли попробовать бесплатно?",
      answer: isEnglish
        ? "There is no fully free run right now. The first-touch option is a trial pack for 199 RUB with 1 request, enough to test VizuAI on your own task."
        : "Полностью бесплатного запуска сейчас нет. Для первого знакомства доступен пробный пакет за 199 ₽ — это 1 запрос, которого достаточно, чтобы попробовать сервис на своей задаче и оценить результат.",
    },
    {
      question: isEnglish ? "Where should I write with questions or issues?" : "Куда обращаться с вопросами, предложениями или ошибками?",
      answer: isEnglish
        ? "Write to us in Telegram, Instagram, or by email at owner@vizuai.example. We can help with billing, launches, and result quality."
        : "Пишите нам в Telegram, Instagram или на почту owner@vizuai.example — поможем разобраться с оплатой, запуском и результатами.",
    },
  ];

  return (
    <section className="bg-[#F5F3E7] px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <h2 className="mb-4 text-center text-3xl font-bold text-[#2C3419] sm:text-4xl md:text-5xl">
          {isEnglish ? "Frequently asked questions" : "Частые вопросы"}
        </h2>
        <p className="mb-12 text-center text-base text-gray-600 sm:text-lg">
          {isEnglish ? "Answers to the most common questions about VizuAI" : "Ответы на самые популярные вопросы о VizuAI"}
        </p>
        
        <Accordion.Root type="single" collapsible className="space-y-4">
          {faqs.map((faq, index) => (
            <Accordion.Item 
              key={index} 
              value={`item-${index}`}
              className="bg-white rounded-xl shadow-md overflow-hidden"
            >
              <Accordion.Header>
                <Accordion.Trigger className="group flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-gray-50 sm:px-6 sm:py-5">
                  <span className="pr-4 text-base font-semibold text-[#2C3419] sm:text-lg">
                    {faq.question}
                  </span>
                  <ChevronDown className="w-5 h-5 text-[#7A8B4A] transition-transform duration-300 group-data-[state=open]:rotate-180 flex-shrink-0" />
                </Accordion.Trigger>
              </Accordion.Header>
              <Accordion.Content className="overflow-hidden data-[state=open]:animate-accordion-down data-[state=closed]:animate-accordion-up">
                <div className="px-5 pb-4 leading-relaxed text-gray-700 sm:px-6 sm:pb-5">
                  {faq.answer}
                </div>
              </Accordion.Content>
            </Accordion.Item>
          ))}
        </Accordion.Root>
      </div>
    </section>
  );
}
