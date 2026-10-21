import type { BimElementProperties, BimViewerManifest } from "../types";

/** Read-only source port. Canonical domains supply their own authorized routes. */
export type BimViewerSourceProvider = {
  source: () => Promise<Blob>;
  manifest: () => Promise<BimViewerManifest>;
  elementProperties: (key: string) => Promise<BimElementProperties>;
};
