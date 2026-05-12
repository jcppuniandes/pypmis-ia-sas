type ProductLogoProps = {
  compact?: boolean;
};

export default function ProductLogo({ compact = false }: ProductLogoProps) {
  return (
    <div className={compact ? "productLogo compact" : "productLogo"}>
      <svg
        aria-label="P&P Control Intelligence logo"
        className="productLogoMark"
        role="img"
        viewBox="0 0 64 64"
      >
        <title>P&P Control Intelligence logo</title>
        <defs>
          <linearGradient id="pypmisMarkGradient" x1="10" x2="54" y1="8" y2="56">
            <stop offset="0" stopColor="#10a6a8" />
            <stop offset="0.58" stopColor="#136f8f" />
            <stop offset="1" stopColor="#17212b" />
          </linearGradient>
        </defs>
        <rect fill="#ffffff" height="56" rx="14" width="56" x="4" y="4" />
        <path
          d="M18 45V18h17.5c6.5 0 10.7 3.9 10.7 9.6 0 5.9-4.3 9.9-10.7 9.9H27v7.5h-9Zm9-15.3h8.1c2.4 0 4-1.1 4-3.1 0-1.9-1.6-3-4-3H27v6.1Z"
          fill="url(#pypmisMarkGradient)"
        />
        <path
          d="M19 48c14.7-1.3 25.4-8.3 32-20"
          fill="none"
          stroke="#d89b2b"
          strokeLinecap="round"
          strokeWidth="4"
        />
        <circle cx="51" cy="28" fill="#d89b2b" r="4.2" />
      </svg>
      <div>
        <strong>P&Pmis Ai</strong>
        {!compact && <span>Control Intelligence SaaS</span>}
      </div>
    </div>
  );
}
