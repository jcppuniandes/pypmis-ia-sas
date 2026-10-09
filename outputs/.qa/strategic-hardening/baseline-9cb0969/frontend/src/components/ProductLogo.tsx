type ProductLogoProps = {
  compact?: boolean;
};

export default function ProductLogo({ compact = false }: ProductLogoProps) {
  return (
    <div className={compact ? "productLogo compact" : "productLogo"}>
      <img
        alt="P&Pmis Construction AI logo"
        className="productLogoMark"
        draggable="false"
        src="/pypmis-construction-ai-logo.png"
      />
      <div>
        <strong>P&Pmis Construction AI</strong>
        {!compact && <span>Control Intelligence</span>}
      </div>
    </div>
  );
}
