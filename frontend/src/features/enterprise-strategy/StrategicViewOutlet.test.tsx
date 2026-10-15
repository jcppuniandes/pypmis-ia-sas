import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StrategicViewOutlet from "./StrategicViewOutlet";

vi.mock("../enterprise-structure/pages/AdminEnterpriseStructurePage", () => ({
  default: ({ initialTab }: { initialTab?: string }) => <div>Enterprise ADMIN configuration · {initialTab}</div>,
}));

vi.mock("../business-analysis/BusinessAnalysisAdminView", () => ({
  default: () => <div>Business Analysis ADMIN editor</div>,
}));
vi.mock("../commercial-strategy/CommercialStrategyAdminView", () => ({
  default: () => <div>Commercial Strategy ADMIN editor</div>,
}));
vi.mock("../commercial-strategy/CommercialStrategyWorkspace", () => ({
  default: () => <div>Commercial Strategy USER workspace</div>,
}));
vi.mock("../strategic-benefits/StrategicBenefitsAdminView", () => ({
  default: () => <div>Strategic Benefits ADMIN editor</div>,
}));
vi.mock("../strategic-benefits/StrategicBenefitsWorkspace", () => ({
  default: () => <div>Strategic Benefits USER workspace</div>,
}));
vi.mock("../portfolio-review/PortfolioReviewAdminView", () => ({
  default: () => <div>Periodic Portfolio Review ADMIN policy</div>,
}));
vi.mock("../portfolio-review/PortfolioReviewWorkspace", () => ({
  default: ({ initialView }: { initialView?: string }) => (
    <div>Periodic Portfolio Review USER workspace · {initialView}</div>
  ),
}));
vi.mock("../basic-data/BasicDataWorkspace", () => ({ default: () => <div>Basic Data USER evidence</div> }));
vi.mock("../basic-data/BasicDataAdminView", () => ({ default: () => <div>Basic Data ADMIN policy</div> }));
vi.mock("../owner-capability/OwnerCapabilityWorkspace", () => ({
  default: () => <div>Owner Capability USER assessments</div>,
}));
vi.mock("../owner-capability/OwnerCapabilityAdminView", () => ({
  default: () => <div>Owner Capability ADMIN policy</div>,
}));
vi.mock("../qra-foundation/QraFoundationWorkspace", () => ({
  default: ({ initialView }: { initialView?: string }) => <div>QRA Foundation USER · {initialView}</div>,
}));
vi.mock("../qra-foundation/QraFoundationAdminView", () => ({
  default: () => <div>QRA Foundation ADMIN methodology</div>,
}));
vi.mock("../qra-engine/QraEngineWorkspace", () => ({
  default: ({ initialView }: { initialView?: string }) => <div>QRA Engine USER · {initialView}</div>,
}));
vi.mock("../risk-governance/RiskGovernanceAdminView", () => ({
  default: () => <div>Risk Governance ADMIN policy</div>,
}));

describe("StrategicViewOutlet", () => {
  it("routes Composition Rules to reusable ADMIN configuration without a live Workspace creation form", () => {
    const { rerender } = render(
      <StrategicViewOutlet
        canConfigure
        mode="admin"
        onNavigate={() => undefined}
        token="admin"
        view="enterprise-workspace-structure"
      />
    );
    expect(screen.getByText("Enterprise ADMIN configuration · rules")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /crear workspace/i })).not.toBeInTheDocument();
    rerender(
      <StrategicViewOutlet
        canConfigure={false}
        mode="admin"
        onNavigate={() => undefined}
        token="user"
        view="enterprise-workspace-structure"
      />
    );
    expect(screen.getByRole("alert", { name: "Strategic configuration access denied" })).toBeInTheDocument();
    expect(screen.queryByText("Enterprise ADMIN configuration · rules")).not.toBeInTheDocument();
    rerender(
      <StrategicViewOutlet
        canConfigure
        mode="user"
        onNavigate={() => undefined}
        token="admin"
        view="enterprise-workspace-structure"
      />
    );
    expect(screen.queryByText("Enterprise ADMIN configuration · rules")).not.toBeInTheDocument();
  });

  it("renders engine USER routes through the existing strategic outlet and rejects ADMIN mode", () => {
    const { rerender } = render(
      <StrategicViewOutlet canConfigure={false} mode="user" onNavigate={() => undefined} token="user" view="qra-runs" />
    );
    expect(screen.getByText("QRA Engine USER · qra-runs")).toBeInTheDocument();
    for (const view of [
      "qra-approved-models",
      "qra-cost-results",
      "qra-schedule-results",
      "qra-percentiles",
      "qra-sensitivity",
      "qra-convergence",
      "qra-run-evidence",
      "qra-run-comparison",
      "qra-run-history",
    ] as const) {
      rerender(
        <StrategicViewOutlet canConfigure={false} mode="user" onNavigate={() => undefined} token="user" view={view} />
      );
      expect(screen.getByText(`QRA Engine USER · ${view}`)).toBeInTheDocument();
    }
    rerender(
      <StrategicViewOutlet canConfigure mode="admin" onNavigate={() => undefined} token="admin" view="qra-runs" />
    );
    expect(screen.queryByText(/QRA Engine USER/)).not.toBeInTheDocument();
  });
  it("renders canonical QRA USER views without exposing methodology mutation", () => {
    const { rerender } = render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="user"
        onNavigate={() => undefined}
        token="user"
        view="qra-foundation"
      />
    );
    expect(screen.getByText("QRA Foundation USER · qra-foundation")).toBeInTheDocument();
    for (const view of ["qra-schedule-source-readiness", "qra-model-definition", "qra-foundation-history"] as const) {
      rerender(
        <StrategicViewOutlet canConfigure={false} mode="user" onNavigate={() => undefined} token="user" view={view} />
      );
      expect(screen.getByText(`QRA Foundation USER · ${view}`)).toBeInTheDocument();
    }
    expect(screen.queryByText("QRA Foundation ADMIN methodology")).not.toBeInTheDocument();
  });
  it("protects the QRA ADMIN direct route before rendering policy controls", () => {
    const { rerender } = render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="admin"
        onNavigate={() => undefined}
        token="user"
        view="qra-methodology-source-readiness"
      />
    );
    expect(screen.getByRole("alert", { name: "Strategic configuration access denied" })).toBeInTheDocument();
    expect(screen.queryByText("QRA Foundation ADMIN methodology")).not.toBeInTheDocument();
    rerender(
      <StrategicViewOutlet
        canConfigure
        mode="admin"
        onNavigate={() => undefined}
        token="admin"
        view="qra-methodology-source-readiness"
      />
    );
    expect(screen.getByText("QRA Foundation ADMIN methodology")).toBeInTheDocument();
  });
  it("separates Owner Capability USER assessments from permission-protected ADMIN configuration", () => {
    const { rerender } = render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="user"
        onNavigate={() => undefined}
        token="user"
        view="owner-capability-readiness"
      />
    );
    expect(screen.getByText("Owner Capability USER assessments")).toBeInTheDocument();
    rerender(
      <StrategicViewOutlet
        canConfigure={false}
        mode="admin"
        onNavigate={() => undefined}
        token="user"
        view="owner-capability-configuration"
      />
    );
    expect(screen.getByRole("alert", { name: "Strategic configuration access denied" })).toBeInTheDocument();
    expect(screen.queryByText("Owner Capability ADMIN policy")).not.toBeInTheDocument();
    rerender(
      <StrategicViewOutlet
        canConfigure
        mode="admin"
        onNavigate={() => undefined}
        token="config"
        view="owner-capability-configuration"
      />
    );
    expect(screen.getByText("Owner Capability ADMIN policy")).toBeInTheDocument();
  });
  it("renders Wave 2B USER evidence and independently guards both ADMIN policy routes", () => {
    const { rerender } = render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="user"
        onNavigate={() => undefined}
        token="user"
        view="basic-data-readiness"
      />
    );
    expect(screen.getByText("Basic Data USER evidence")).toBeInTheDocument();
    for (const view of ["risk-governance-configuration", "basic-data-configuration"] as const) {
      rerender(
        <StrategicViewOutlet canConfigure={false} mode="admin" onNavigate={() => undefined} token="user" view={view} />
      );
      expect(screen.getByRole("alert", { name: "Strategic configuration access denied" })).toBeInTheDocument();
    }
    rerender(
      <StrategicViewOutlet
        canConfigure
        mode="admin"
        onNavigate={() => undefined}
        token="admin"
        view="risk-governance-configuration"
      />
    );
    expect(screen.getByText("Risk Governance ADMIN policy")).toBeInTheDocument();
    rerender(
      <StrategicViewOutlet
        canConfigure
        mode="admin"
        onNavigate={() => undefined}
        token="admin"
        view="basic-data-configuration"
      />
    );
    expect(screen.getByText("Basic Data ADMIN policy")).toBeInTheDocument();
  });
  it("blocks a direct ADMIN configuration view without can_configure", () => {
    render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="admin"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="business-analysis-configuration"
      />
    );

    expect(screen.getByRole("alert", { name: "Strategic configuration access denied" })).toHaveAttribute(
      "data-control-classification",
      "ADMIN_CONFIGURATION"
    );
    expect(screen.getByText("Configuration access required")).toBeInTheDocument();
    expect(screen.queryByText("Business Analysis ADMIN editor")).not.toBeInTheDocument();
  });

  it("renders the ADMIN configuration view with can_configure", () => {
    render(
      <StrategicViewOutlet
        canConfigure
        mode="admin"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="business-analysis-configuration"
      />
    );

    expect(screen.getByText("Business Analysis ADMIN editor")).toBeInTheDocument();
    expect(screen.getByText("Business Analysis Configuration")).toBeInTheDocument();
  });

  it("resolves Commercial Strategy USER and ADMIN views through the canonical outlet", () => {
    const { rerender } = render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="user"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="commercial-strategy-risk-allocation"
      />
    );
    expect(screen.getByText("Commercial Strategy USER workspace")).toBeInTheDocument();
    expect(screen.getByText("Risk Allocation")).toBeInTheDocument();

    rerender(
      <StrategicViewOutlet
        canConfigure
        mode="admin"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="commercial-strategy-configuration"
      />
    );
    expect(screen.getByText("Commercial Strategy ADMIN editor")).toBeInTheDocument();
    expect(screen.getByText("Commercial Strategy Configuration")).toBeInTheDocument();
  });

  it("blocks the direct Commercial Strategy ADMIN route without can_configure", () => {
    render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="admin"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="commercial-strategy-configuration"
      />
    );
    expect(screen.getByRole("alert", { name: "Strategic configuration access denied" })).toBeInTheDocument();
    expect(screen.queryByText("Commercial Strategy ADMIN editor")).not.toBeInTheDocument();
  });

  it("resolves Strategic Benefits USER and ADMIN views through the canonical outlet", () => {
    const { rerender } = render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="user"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="strategic-benefits-traceability"
      />
    );
    expect(screen.getByText("Strategic Benefits USER workspace")).toBeInTheDocument();
    expect(screen.getByText("Traceability")).toBeInTheDocument();

    rerender(
      <StrategicViewOutlet
        canConfigure
        mode="admin"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="benefits-configuration"
      />
    );
    expect(screen.getByText("Strategic Benefits ADMIN editor")).toBeInTheDocument();
    expect(screen.getByText("Benefits Configuration")).toBeInTheDocument();
  });

  it("blocks the direct Benefits ADMIN route without can_configure", () => {
    render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="admin"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="benefits-configuration"
      />
    );
    expect(screen.getByRole("alert", { name: "Strategic configuration access denied" })).toBeInTheDocument();
    expect(screen.queryByText("Strategic Benefits ADMIN editor")).not.toBeInTheDocument();
  });

  it("resolves Portfolio Review USER sessions and keeps the ADMIN configuration route permission-protected", () => {
    const { rerender } = render(
      <StrategicViewOutlet
        canConfigure={false}
        mode="user"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="portfolio-review-actions"
      />
    );
    expect(screen.getByText(/Periodic Portfolio Review USER workspace · portfolio-review-actions/)).toBeInTheDocument();
    expect(screen.getByText("Actions")).toBeInTheDocument();

    rerender(
      <StrategicViewOutlet
        canConfigure={false}
        mode="admin"
        onNavigate={() => undefined}
        token="authenticated-token"
        view="portfolio-review-configuration"
      />
    );
    expect(screen.getByRole("alert", { name: "Strategic configuration access denied" })).toBeInTheDocument();
    expect(screen.queryByText("Periodic Portfolio Review ADMIN policy")).not.toBeInTheDocument();
  });
});
