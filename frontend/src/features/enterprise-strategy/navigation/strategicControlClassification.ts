export const STRATEGIC_CONTROL_CLASSIFICATIONS = [
  "USER_TRANSACTION",
  "ADMIN_CONFIGURATION",
  "READ_ONLY_SHARED",
] as const;

export type StrategicControlClassification = (typeof STRATEGIC_CONTROL_CLASSIFICATIONS)[number];

export const STRATEGIC_PERMISSION_BY_CLASSIFICATION = {
  USER_TRANSACTION: "authenticated",
  ADMIN_CONFIGURATION: "can_configure",
  READ_ONLY_SHARED: "authenticated",
} as const satisfies Record<StrategicControlClassification, "authenticated" | "can_configure">;
