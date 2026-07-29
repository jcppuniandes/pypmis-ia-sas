import type { AppShellCtx } from "./AppShellCtx";

export default function Sidebar({ ctx }: { ctx: AppShellCtx }) {
  const { activeView, setActiveView, primaryNavigatorItems, secondaryNavigatorItems } = ctx;
  return (
    <aside className="navigatorRail" aria-label="Project controls navigation">
      <div className="navigatorHeader">
        <strong>Project Controls</strong>
        <span>Navigator</span>
      </div>
      {primaryNavigatorItems.map((item) => (
        <button
          className={activeView === item.key ? "navigatorItem active" : "navigatorItem"}
          key={item.key}
          onClick={() => setActiveView(item.key)}
          type="button"
        >
          <span>{item.label}</span>
          <strong>{item.count}</strong>
        </button>
      ))}
      <div className="navigatorDivider">
        <span>More</span>
      </div>
      {secondaryNavigatorItems.map((item) => (
        <button
          className={activeView === item.key ? "navigatorItem active" : "navigatorItem"}
          key={item.key}
          onClick={() => setActiveView(item.key)}
          type="button"
        >
          <span>{item.label}</span>
          <strong>{item.count}</strong>
        </button>
      ))}
    </aside>
  );
}
