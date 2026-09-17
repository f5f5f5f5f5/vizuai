import { Examples } from "@/app/components/Examples";
import { PublicPageShell } from "@/app/components/PublicPageShell";
import { useLocale } from "@/app/i18n";

export function ExamplesPage() {
  const { isEnglish } = useLocale();
  return (
    <PublicPageShell
      eyebrow={isEnglish ? "Examples" : "Примеры работ"}
      title={isEnglish ? "VizuAI examples" : "Примеры работ VizuAI"}
      description={
        isEnglish
          ? "A set of real examples to quickly evaluate result style, detail level, and how VizuAI behaves across different spaces and tasks."
          : "Подборка реальных примеров, чтобы можно было быстро оценить характер результата, уровень деталей и то, как VizuAI работает с разными пространствами и задачами."
      }
    >
      <Examples showHeader={false} showPrompt={false} showExtended />
    </PublicPageShell>
  );
}
