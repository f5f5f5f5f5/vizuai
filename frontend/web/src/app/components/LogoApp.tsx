import logoImage from "../../assets/7cbb2b7ef052fc6825d19abf368ad60810f3653d.png";
import logoImageDark from "../../assets/32debdc590b6add26e6f360f6d7aba4bcf77279c.png";
import { useTheme } from "../contexts/ThemeContext";

interface LogoAppProps {
  className?: string;
  height?: number;
}

export function LogoApp({ className = "", height = 48 }: LogoAppProps) {
  const { isDarkMode } = useTheme();

  return (
    <img 
      src={isDarkMode ? logoImageDark : logoImage} 
      alt="VizuAI" 
      className={`object-contain ${className}`}
      style={{ 
        height: `${height}px`,
        display: 'block'
      }}
    />
  );
}
