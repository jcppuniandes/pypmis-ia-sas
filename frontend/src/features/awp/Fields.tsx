import type { ReactNode } from "react";
import type { AwpOverview } from "./types";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="awpField">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function NamedSelect({
  label,
  value,
  onChange,
  options,
  optional = true,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string | number; label: string }[];
  optional?: boolean;
}) {
  return (
    <Field label={label}>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} required={!optional}>
        {optional ? (
          <option value="">Sin selección</option>
        ) : (
          <option value="" disabled>
            Seleccionar
          </option>
        )}
        {options.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </Field>
  );
}
export function MappingTarget({
  data,
  kind,
  target,
  setTarget,
  versionId,
  setVersionId,
  activity,
  setActivity,
}: {
  data: AwpOverview;
  kind: string;
  target: string;
  setTarget: (v: string) => void;
  versionId: string;
  setVersionId: (v: string) => void;
  activity: string;
  setActivity: (v: string) => void;
}) {
  const schedule = data.schedule_versions.find((row) => row.id === Number(versionId));
  const options =
    kind === "SCOPE"
      ? data.scope_items
          .filter((row) => data.current_scope_item_ids.includes(row.id))
          .map((row) => ({ value: row.id, label: `${row.scope_code} · ${row.name}` }))
      : kind === "PLAN"
        ? data.plan_items
            .filter((row) => !row.status || row.status === "PUBLISHED")
            .map((row) => ({ value: row.id, label: `${row.code} · ${row.name}` }))
        : kind === "PACKAGE"
          ? data.packages.map((row) => ({ value: row.id, label: `${row.package_code} · ${row.name}` }))
          : data.cwas.map((row) => ({ value: row.id, label: `${row.code} · ${row.name}` }));
  return kind === "ACTIVITY" ? (
    <>
      <NamedSelect
        label="Mapping Schedule Version"
        value={versionId}
        onChange={setVersionId}
        optional={false}
        options={data.schedule_versions.map((row) => ({
          value: row.id,
          label: `#${row.id} · ${row.status} · ${row.data_date ?? "Sin Data Date"}`,
        }))}
      />
      <NamedSelect
        label="Mapping Activity"
        value={activity}
        onChange={setActivity}
        optional={false}
        options={(schedule?.snapshot_json.activities ?? []).map((row) => ({
          value: row.external_id,
          label: `${row.code ?? row.external_id} · ${row.name ?? ""}`,
        }))}
      />
    </>
  ) : (
    <NamedSelect label={`Mapping ${kind}`} value={target} onChange={setTarget} options={options} optional={false} />
  );
}
