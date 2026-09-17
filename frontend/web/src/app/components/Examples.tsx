import { useState } from "react";
import { useLocale } from "@/app/i18n";

import example1Before from "../../assets/2ccb8dd795614442ebc9d7241dbfdddb492a6ae7.png";
import example1After from "../../assets/5915b0d8423e7ef6668b6a3bf29444375ef94372.png";
import example2Before from "../../assets/6bbc8feccf78da1ca33278afd7dd45daaf631a56.png";
import example2After from "../../assets/3419a795d51910764a9ece34d2aab8d2df79ce84.png";
import example3Before from "../../assets/e2f3bb53123a257c4a653532feccecce384795a3.png";
import example3After from "../../assets/220ccda226f4383ca85067a089516511273ccb63.png";
import example4Before from "../../assets/7d1c6a1b7d0d8e6796e80a5dcf28db06bfd18f00.png";
import example4After from "../../assets/e3df1b130e8c9718ff4c91805c02bfa0fff14d87.png";
import example5Before from "../../assets/02465be905f0e22fcbc09db3f93a6f06fe9df008.png";
import example5After from "../../assets/a13b3468794d7245a25420b3e73fdf1b04c7c71f.png";
import example6Before from "../../assets/f6ccf451b1e98adda87acfcc089b3557f7d7af0f.png";
import example6After from "../../assets/5c16cfcf5ac27d20d19a8877166c67e8f2f2c145.png";
import example7Before from "../../assets/examples/example7-before.jpg";
import example7After from "../../assets/examples/example7-after.jpg";
import example8Before from "../../assets/examples/example8-before.jpg";
import example8After from "../../assets/examples/example8-after.jpg";
import example9Before from "../../assets/examples/example9-before.jpg";
import example9After from "../../assets/examples/example9-after.jpg";
import example10Before from "../../assets/examples/example10-before.jpg";
import example10After from "../../assets/examples/example10-after.jpg";
import example11Before from "../../assets/examples/example11-before.jpg";
import example11After from "../../assets/examples/example11-after.jpg";
import example12Before from "../../assets/examples/example12-before.jpg";
import example12After from "../../assets/examples/example12-after.jpg";
import example13Before from "../../assets/examples/example13-before.jpg";
import example13After from "../../assets/examples/example13-after.jpg";

const examples = [
  {
    id: 1,
    before: example5Before,
    after: example5After,
    promptRu: "Спальня в африканском современном стиле. Деревянные балки на потолке, плетеные светильники. Панели из дерева и камня с первобытными рисунками. Деревянная кровать, большой ковер, зеркало. Цвета: коричневый, бежевый, охра, анималистичные принты.",
    promptEn: "Bedroom in a modern African style. Wooden ceiling beams, woven pendant lights. Wood and stone wall panels with primitive-inspired patterns. Wooden bed, large rug, mirror. Colors: brown, beige, ochre, animal-print accents.",
  },
  {
    id: 2,
    before: example2Before,
    after: example2After,
    promptRu: "Современный ремонт в ванной комнате. Натуральный камень, грязно-голубой цвет, вертикальная узкая плитка. Сантехника белого цвета, унитаз голубой, большое зеркало с подсветкой.",
    promptEn: "Modern bathroom renovation. Natural stone, dusty blue tones, narrow vertical tile. White sanitary fixtures, blue toilet, large backlit mirror.",
  },
  {
    id: 3,
    before: example3Before,
    after: example3After,
    promptRu: "Комната для мальчика 5 лет. Цвета темно-синий, голубой. Рисунки с животными на одной стене. Кровать с мягкими бортиками, шведская стенка, растущий стол и стул, шкаф с открытыми полками для игрушек.",
    promptEn: "Room for a 5-year-old boy. Dark blue and light blue palette. Animal illustrations on one wall. Bed with soft sides, wall bars, adjustable desk and chair, cabinet with open shelves for toys.",
  },
  {
    id: 4,
    before: example6Before,
    after: example6After,
    promptRu: "Кухня в современном индустриальном стиле. Гарнитур до потолка с мятными фасадами, фартук из белой узкой плитки с красной затиркой. Остров с варочной панелью, серые барные стулья, изящные светильники.",
    promptEn: "Kitchen in a modern industrial style. Full-height cabinetry with mint fronts, white narrow-tile backsplash with red grout. Island with cooktop, gray bar stools, elegant lighting.",
  },
  {
    id: 5,
    before: example1Before,
    after: example1After,
    promptRu: "Гостиная в бежевых и темно-коричневых цветах. Большой светлый низкий диван на ножках, кресло с пуфиком, домик для кошки, стол из слэба, теплый свет, красивые шторы.",
    promptEn: "Living room in beige and dark brown tones. Large light low-profile sofa on legs, armchair with ottoman, cat house, slab coffee table, warm lighting, elegant curtains.",
  },
  {
    id: 6,
    before: example4Before,
    after: example4After,
    promptRu: "Гостиная в стиле Earthy Eclectic. Цвета: терракотовый, охра, оливковый. Большой необычный диван, картины, красивые шторы и растения. Новая люстра в стиле. Телевизор оставить.",
    promptEn: "Living room in an earthy eclectic style. Colors: terracotta, ochre, olive. Large sculptural sofa, artwork, elegant curtains, plants. New statement chandelier. Keep the TV.",
  },
  {
    id: 7,
    before: example7Before,
    after: example7After,
    promptRu: "Это кухня. Пол нужно сделать кварц винил елочкой, цвет светло-бежевый. Нижние шкафы кухни под дерево, верхние оливкового цвета. Под потолком закрытые полки из тонированного бронзового стекла. Фартук в двух цветах: темно-болотный и белый, вертикальная узкая плитка. Встроенный холодильник, СВЧ и духовка. Стены с градиентной штукатуркой от оливкового у пола к белому на потолке. Деревянный стол на 4 персоны, стулья с терракотовой обивкой, добавить еще терракотовых элементов декора.",
    promptEn: "This is a kitchen. Replace the floor with light beige herringbone LVT. Lower cabinets in wood, upper cabinets in olive. Add closed upper storage in tinted bronze glass near the ceiling. Two-tone backsplash in dark swamp green and white using narrow vertical tile. Built-in fridge, microwave, and oven. Gradient plaster walls from olive near the floor to white at the ceiling. Wooden dining table for four, chairs with terracotta upholstery, and a few more terracotta decor accents.",
  },
  {
    id: 8,
    before: example8Before,
    after: example8After,
    promptRu: "Это зал в кофейне. Надо полностью обновить интерьер: сделать белым, минималистичным, с металлическими акцентами. Убрать розовый цвет и дерево. На стене сделать большую стильную надпись coffee.",
    promptEn: "This is a coffee shop seating area. Fully redesign the interior: make it white, minimal, with metallic accents. Remove the pink and wood tones. Add a large stylish coffee sign on the wall.",
  },
  {
    id: 9,
    before: example9Before,
    after: example9After,
    promptRu: "Это будущая кухня. Нужно поставить кухонный гарнитур буквой П. Верхние полки только по центральной стене. Мойка около окна слева. Нижние шкафы цвета тёмный шоколад. Верхние бежевые, с гофре. Фартук из натурального камня с крупными разводами. Встроенные СВЧ, духовка и холодильник.",
    promptEn: "This will be a future kitchen. Add a U-shaped kitchen layout. Upper cabinets only on the central wall. Sink near the window on the left. Lower cabinets in dark chocolate, upper cabinets in beige with fluted fronts. Natural stone backsplash with bold veining. Built-in microwave, oven, and refrigerator.",
  },
  {
    id: 10,
    before: example10Before,
    after: example10After,
    promptRu: "Это будет детская комната для двух детей 3 и 5 лет, мальчика и девочки. Цвета: пыльно-розовый и цвет морской волны. Нужно поставить две кровати с мягкими бортиками, сделать хранение для игрушек и одежды, положить ковер, поставить детский стол и стул, повесить необычную люстру и добавить игрушечный вигвам.",
    promptEn: "This will be a kids' room for two children, ages 3 and 5, a boy and a girl. Colors: dusty pink and deep aqua. Add two beds with soft rails, storage for toys and clothes, a rug, a children's table and chair, an unusual chandelier, and a play teepee.",
  },
  {
    id: 11,
    before: example11Before,
    after: example11After,
    promptRu: "Это моя гостиная, ее нужно полностью обновить. Хочу стиль Moody modern, чтобы выглядело дорого и эффектно. Цвета: шоколадный, тёмно-оливковый, графит. Диван сделать большим, низким и мягким. Заменить шторы, люстру и ковер.",
    promptEn: "This is my living room and it needs a full refresh. I want a moody modern style that feels expensive and dramatic. Colors: chocolate, dark olive, graphite. Make the sofa large, low, and soft. Replace the curtains, chandelier, and rug.",
  },
  {
    id: 12,
    before: example12Before,
    after: example12After,
    promptRu: "Это моя гостиная. Хочу обновить ее для жизни молодой семьи с ребенком. Сделай эко-стиль, использовать дерево, много света и растения.",
    promptEn: "This is my living room. I want to update it for a young family with a child. Make it eco-style, use wood, plenty of light, and plants.",
  },
  {
    id: 13,
    before: example13Before,
    after: example13After,
    promptRu: "Это моя гостиная. В нее надо добавить уюта и сделать более теплой. Положить ковер, подушки на диван, можно заменить шторы. Заменить журнальный стол и стеклянные тумбы.",
    promptEn: "This is my living room. I want it to feel warmer and more inviting. Add a rug and pillows to the sofa, replace the curtains if needed. Replace the coffee table and the glass side tables.",
  }
];

const landingExampleIds = new Set([1, 2, 3, 4, 5, 6]);

type ExamplesProps = {
  showHeader?: boolean;
  showPrompt?: boolean;
  showExtended?: boolean;
};

export function Examples({
  showHeader = true,
  showPrompt = true,
  showExtended = false,
}: ExamplesProps) {
  const { isEnglish } = useLocale();
  const visibleExamples = showExtended
    ? examples
    : examples.filter((example) => landingExampleIds.has(example.id));

  return (
    <section id="examples" className="bg-[#F5F3E7] px-6 py-20 sm:py-24">
      <div className="max-w-7xl mx-auto">
        {showHeader ? (
          <div className="text-center mb-16">
            <h2 className="mb-4 text-3xl text-[#2C3419] sm:text-4xl md:text-5xl">
              {isEnglish ? "Selected examples" : "Примеры наших работ"}
            </h2>
            <p className="text-base text-[#5A6B3A] sm:text-lg">
              {isEnglish ? "On desktop, hover over the image to reveal the original photo" : "На компьютере наведите на изображение, чтобы увидеть исходное фото"}
            </p>
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3 md:gap-8">
          {visibleExamples.map((example) => (
            <ExampleCard key={example.id} example={example} showPrompt={showPrompt} isEnglish={isEnglish} />
          ))}
        </div>
      </div>
    </section>
  );
}

function ExampleCard({
  example,
  showPrompt,
  isEnglish,
}: {
  example: (typeof examples)[number];
  showPrompt: boolean;
  isEnglish: boolean;
}) {
  const [showBefore, setShowBefore] = useState(false);

  return (
    <div className="group relative overflow-hidden rounded-2xl bg-white shadow-xl">
      <div className="relative aspect-[4/3] overflow-hidden">
        <img
          src={example.after}
          alt={`Пример работы ${example.id} - после`}
          loading="lazy"
          decoding="async"
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${
            showBefore ? "opacity-0" : "opacity-100"
          } md:opacity-100 md:group-hover:opacity-0`}
        />
        <img
          src={example.before}
          alt={`Пример работы ${example.id} - до`}
          loading="lazy"
          decoding="async"
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${
            showBefore ? "opacity-100" : "opacity-0"
          } md:opacity-0 md:group-hover:opacity-100`}
        />

        <div className="absolute right-3 top-3 rounded-lg bg-black/70 px-3 py-1.5 text-xs font-medium text-white sm:right-4 sm:top-4 sm:px-4 sm:py-2 sm:text-sm">
          <span className="md:hidden">{showBefore ? (isEnglish ? "Before" : "До") : isEnglish ? "After" : "После"}</span>
          <span className="hidden md:inline group-hover:hidden">{isEnglish ? "After" : "После"}</span>
          <span className="hidden md:group-hover:inline">{isEnglish ? "Before" : "До"}</span>
        </div>
      </div>

      <div className="border-b border-[#E7E2CC] px-5 py-3 md:hidden">
        <div className="grid grid-cols-2 gap-2 rounded-xl bg-[#F5F3E7] p-1">
          <button
            type="button"
            onClick={() => setShowBefore(false)}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              !showBefore ? "bg-white text-[#2C3419] shadow-sm" : "text-[#5A6B3A]"
            }`}
          >
            {isEnglish ? "After" : "После"}
          </button>
          <button
            type="button"
            onClick={() => setShowBefore(true)}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              showBefore ? "bg-white text-[#2C3419] shadow-sm" : "text-[#5A6B3A]"
            }`}
          >
            {isEnglish ? "Before" : "До"}
          </button>
        </div>
      </div>

      {showPrompt && (isEnglish ? example.promptEn : example.promptRu).trim() ? (
        <div className="p-5 sm:p-6">
          <p className="text-sm italic text-[#5A6B3A] md:text-base">
            "{isEnglish ? example.promptEn : example.promptRu}"
          </p>
        </div>
      ) : null}
    </div>
  );
}
