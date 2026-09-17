import logoImage from "../../assets/32debdc590b6add26e6f360f6d7aba4bcf77279c.png";

interface LogoProps {
  className?: string;
  height?: number;
}

export function Logo({ className = "", height = 48 }: LogoProps) {
  return (
    <div className="flex items-center mt-6 ml-6">
      <img 
        src={logoImage} 
        alt="VizuAI" 
        className={`object-contain ${className}`}
        style={{ 
          height: `${height}px`,
          display: 'block'
        }}
      />
    </div>
  );
}
