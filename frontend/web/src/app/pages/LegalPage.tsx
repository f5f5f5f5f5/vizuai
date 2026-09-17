import { FileText, Shield, Lock, RotateCcw, Wallet, Mail, Link as LinkIcon, Send } from "lucide-react";
import { useMemo, useState } from "react";
import { useTheme } from "@/app/contexts/ThemeContext";
import { useLocale } from "@/app/i18n";
import { trackPublicClick } from "@/app/lib/analytics/client";

import offerDocument from "../../../../../docs/legal/offer.md?raw";
import consentDocument from "../../../../../docs/legal/pd_consent.md?raw";
import policyDocument from "../../../../../docs/legal/privacy_policy.md?raw";
import refundDocument from "../../../../../docs/legal/refund_policy.md?raw";
import pricingDocument from "../../../../../docs/legal/service_pricing.md?raw";
import contactsDocument from "../../../../../docs/legal/contacts.md?raw";
import affiliateDocument from "../../../../../docs/legal/affiliate_disclosure.md?raw";

type DocumentType =
  | "offer"
  | "consent"
  | "policy"
  | "refund"
  | "pricing"
  | "contacts"
  | "affiliate";

function renderMarkdown(content: string, isDarkMode: boolean) {
  const lines = content.split(/\r?\n/);
  const blocks: Array<{ type: string; value?: string; items?: string[] }> = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let listType: "ul" | "ol" | null = null;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: "p", value: paragraph.join(" ") });
      paragraph = [];
    }
  };

  const flushList = () => {
    if (list.length && listType) {
      blocks.push({ type: listType, items: [...list] });
      list = [];
      listType = null;
    }
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      return;
    }

    if (line.startsWith("# ")) {
      flushParagraph();
      flushList();
      blocks.push({ type: "h1", value: line.slice(2).trim() });
      return;
    }

    if (line.startsWith("## ")) {
      flushParagraph();
      flushList();
      blocks.push({ type: "h2", value: line.slice(3).trim() });
      return;
    }

    if (/^\d+\.\s/.test(line)) {
      flushParagraph();
      if (listType && listType !== "ol") {
        flushList();
      }
      listType = "ol";
      list.push(line.replace(/^\d+\.\s/, "").trim());
      return;
    }

    if (line.startsWith("- ")) {
      flushParagraph();
      if (listType && listType !== "ul") {
        flushList();
      }
      listType = "ul";
      list.push(line.slice(2).trim());
      return;
    }

    flushList();
    paragraph.push(line);
  });

  flushParagraph();
  flushList();

  return blocks.map((block, index) => {
    if (block.type === "h1") {
      return (
        <h2 key={`h1-${index}`} className={`text-2xl font-bold mb-4 ${isDarkMode ? "text-white" : "text-gray-900"}`}>
          {block.value}
        </h2>
      );
    }

    if (block.type === "h2") {
      return (
        <h3 key={`h2-${index}`} className={`text-xl font-semibold mb-3 mt-8 ${isDarkMode ? "text-white" : "text-gray-900"}`}>
          {block.value}
        </h3>
      );
    }

    if (block.type === "ul") {
      return (
        <ul key={`ul-${index}`} className={`list-disc ml-6 space-y-2 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
          {block.items?.map((item, itemIndex) => <li key={`${index}-${itemIndex}`}>{item}</li>)}
        </ul>
      );
    }

    if (block.type === "ol") {
      return (
        <ol key={`ol-${index}`} className={`list-decimal ml-6 space-y-2 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
          {block.items?.map((item, itemIndex) => <li key={`${index}-${itemIndex}`}>{item}</li>)}
        </ol>
      );
    }

    return (
      <p key={`p-${index}`} className={`mb-4 ${isDarkMode ? "text-gray-300" : "text-gray-700"}`}>
        {block.value}
      </p>
    );
  });
}

export function LegalPage() {
  const { isDarkMode } = useTheme();
  const { isEnglish } = useLocale();
  const [activeTab, setActiveTab] = useState<DocumentType>("offer");

  const tabs = [
    { id: "offer" as DocumentType, label: "Публичная оферта", icon: FileText },
    { id: "consent" as DocumentType, label: "Согласие на обработку ПД", icon: Shield },
    { id: "policy" as DocumentType, label: "Политика обработки ПД", icon: Lock },
    { id: "refund" as DocumentType, label: "Политика возвратов", icon: RotateCcw },
    { id: "pricing" as DocumentType, label: "Цены и услуги", icon: Wallet },
    { id: "contacts" as DocumentType, label: "Контакты", icon: Mail },
    { id: "affiliate" as DocumentType, label: "Партнёрские ссылки", icon: LinkIcon },
  ];

  const documents = useMemo(
    () => ({
      offer: offerDocument,
      consent: consentDocument,
      policy: policyDocument,
      refund: refundDocument,
      pricing: pricingDocument,
      contacts: contactsDocument,
      affiliate: affiliateDocument,
    }),
    [],
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:space-y-8 sm:p-8">
      <div>
        <h1 className={`mb-2 text-2xl font-bold sm:text-3xl ${isDarkMode ? "text-white" : "text-gray-900"}`}>{isEnglish ? "Legal documents" : "Юридические документы"}</h1>
        <p className={isDarkMode ? "text-gray-300" : "text-gray-600"}>{isEnglish ? "Legal information and service documents for VizuAI" : "Правовая информация и документы VizuAI"}</p>
        {isEnglish && (
          <div className={`mt-4 rounded-xl px-4 py-3 text-sm ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800 text-gray-300" : "bg-white border border-gray-200 text-gray-700"}`}>
            The source legal documents are currently published in Russian. This page keeps the original texts and provides English navigation for convenience.
          </div>
        )}
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <a
            href="mailto:owner@vizuai.example"
            onClick={() => {
              void trackPublicClick("legal", "email_support_click");
            }}
            className={`inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-semibold transition-colors ${
              isDarkMode
                ? "bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
                : "bg-[#7A8B4A] text-white hover:bg-[#6B7B3F]"
            }`}
          >
            <Mail className="h-4 w-4" />
            {isEnglish ? "Email owner@vizuai.example" : "Написать на owner@vizuai.example"}
          </a>
          <a
            href="https://example.com/support"
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => {
              void trackPublicClick("legal", "telegram_support_click");
            }}
            className={`inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-semibold transition-colors ${
              isDarkMode
                ? "border border-gray-700 bg-[#0F0F0F] text-gray-200 hover:bg-gray-900 hover:text-white"
                : "border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
            }`}
          >
            <Send className="h-4 w-4" />
            {isEnglish ? "Open Telegram" : "Открыть Telegram"}
          </a>
        </div>
      </div>

      <div className={`border-b ${isDarkMode ? "border-gray-800" : "border-gray-200"}`}>
        <div className="flex gap-2 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                void trackPublicClick("legal", "tab_switch", { tab: tab.id });
                setActiveTab(tab.id);
              }}
              className={`flex items-center gap-2 px-6 py-3 font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-[#7A8B4A] text-[#7A8B4A]"
                  : isDarkMode
                    ? "border-transparent text-gray-400 hover:text-gray-300"
                    : "border-transparent text-gray-600 hover:text-gray-900"
              }`}
            >
              <tab.icon className="w-5 h-5" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className={`rounded-2xl p-5 sm:p-8 ${isDarkMode ? "bg-[#0F0F0F] border border-gray-800" : "bg-white border border-gray-200"}`}>
        <div className="space-y-6">
          {renderMarkdown(documents[activeTab], isDarkMode)}
        </div>
      </div>
    </div>
  );
}
