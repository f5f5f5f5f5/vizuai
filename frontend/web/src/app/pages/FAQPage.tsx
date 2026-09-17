import * as Accordion from "@radix-ui/react-accordion";
import { ChevronDown, MessageSquareQuote, ShieldCheck, Wallet, WandSparkles } from "lucide-react";

import { PublicPageShell } from "@/app/components/PublicPageShell";
import { useLocale } from "@/app/i18n";
import { faqByLocale } from "@/app/lib/content/faq";

export function FAQPage() {
  const { isEnglish } = useLocale();
  const faqs = faqByLocale[isEnglish ? "en" : "ru"];
  const highlights = [
    {
      icon: WandSparkles,
      title: isEnglish ? "What VizuAI can do" : "Что умеет VizuAI",
      description: isEnglish
        ? "Interior design from photo, reference-based redesign, and similar furniture search from images."
        : "Дизайн интерьера по фото, сценарий по референсу и поиск похожей мебели по изображению.",
    },
    {
      icon: Wallet,
      title: isEnglish ? "How payment works" : "Как устроена оплата",
      description: isEnglish
        ? "All core scenarios spend requests the same way, and current packs are available after signing in."
        : "Все основные сценарии расходуют запросы одинаково, а актуальные пакеты доступны после входа в приложение.",
    },
    {
      icon: ShieldCheck,
      title: isEnglish ? "What about privacy" : "Что с приватностью",
      description: isEnglish
        ? "This page covers payments, result quality, data storage, and realistic expectations from the service."
        : "На странице собраны ответы не только про оплату и качество, но и про хранение данных и общие ожидания от результата.",
    },
  ];

  return (
    <PublicPageShell
      eyebrow={isEnglish ? "Answers" : "Ответы на вопросы"}
      title={isEnglish ? "Frequently asked questions about VizuAI" : "Частые вопросы о VizuAI"}
      description={
        isEnglish
          ? "One place for answers about running scenarios, payments, result quality, uploads, and support."
          : "Собрали в одном месте ответы про запуск сценариев, оплату, качество результата, загрузку изображений и поддержку."
      }
    >
      <section className="bg-[#F5F3E7] px-6 py-16">
        <div className="mx-auto grid max-w-6xl gap-6 md:grid-cols-3">
          {highlights.map((item) => (
            <div key={item.title} className="rounded-2xl border border-[#E7E2CC] bg-white p-6 shadow-sm">
              <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[#7A8B4A]/10 text-[#7A8B4A]">
                <item.icon className="h-6 w-6" />
              </div>
              <h2 className="mb-2 text-xl text-[#2C3419]">{item.title}</h2>
              <p className="text-sm leading-7 text-[#5A6B3A]">{item.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-4xl">
          <Accordion.Root type="single" collapsible className="space-y-4">
            {faqs.map((faq, index) => (
              <Accordion.Item
                key={faq.question}
                value={`faq-${index}`}
                className="overflow-hidden rounded-2xl border border-[#E7E2CC] bg-[#F5F3E7]"
              >
                <Accordion.Header>
                  <Accordion.Trigger className="group flex w-full items-center justify-between gap-4 px-6 py-5 text-left">
                    <span className="text-base font-semibold text-[#2C3419] sm:text-lg">{faq.question}</span>
                    <ChevronDown className="h-5 w-5 flex-shrink-0 text-[#7A8B4A] transition-transform group-data-[state=open]:rotate-180" />
                  </Accordion.Trigger>
                </Accordion.Header>
                <Accordion.Content className="overflow-hidden data-[state=open]:animate-accordion-down data-[state=closed]:animate-accordion-up">
                  <div className="px-6 pb-6 text-sm leading-8 text-[#5A6B3A] sm:text-base">
                    {faq.answer}
                  </div>
                </Accordion.Content>
              </Accordion.Item>
            ))}
          </Accordion.Root>
        </div>
      </section>

      <section className="bg-white px-6 py-16">
        <div className="mx-auto max-w-4xl rounded-3xl border border-[#E7E2CC] bg-[#F5F3E7] p-8 text-center">
          <div className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-[#7A8B4A] shadow-sm">
            <MessageSquareQuote className="h-7 w-7" />
          </div>
          <h2 className="mb-3 text-3xl text-[#2C3419]">Не нашли нужный ответ?</h2>
          <p className="text-base leading-8 text-[#5A6B3A]">
            {isEnglish
              ? "Write to owner@vizuai.example or contact us in Telegram. If the issue is about billing, launch flow, or result quality, we answer manually and try not to leave gray areas unresolved."
              : "Напишите на owner@vizuai.example или в Telegram. Если вопрос касается качества результата, оплаты или запуска, мы отвечаем вручную и стараемся не оставлять спорные ситуации без решения."}
          </p>
        </div>
      </section>
    </PublicPageShell>
  );
}
