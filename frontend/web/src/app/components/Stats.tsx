import { useLocale } from "@/app/i18n";

export function Stats() {
  const { isEnglish } = useLocale();
  return (
    <section className="py-8 px-6 bg-[#F5F3E7] border-y border-[#7A8B4A]/10">
      <div className="max-w-6xl mx-auto text-center">
        <p className="text-gray-600 text-sm">
          {isEnglish ? (
            <>Already helped bring <span className="font-bold text-[#7A8B4A] text-lg">2000+</span> design ideas to life</>
          ) : (
            <>Уже помогли воплотить <span className="font-bold text-[#7A8B4A] text-lg">2000+</span> дизайнерских идей</>
          )}
        </p>
      </div>
    </section>
  );
}
