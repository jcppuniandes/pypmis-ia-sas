import { useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { Evidence, Records } from "../progress-foundation/Fields";
import { FieldCommandForm, ReadState } from "../field-operations/FieldForms";
import type { FieldSpec } from "../field-operations/formValues";
import { isRow, permits, profilesRoot, rows, text, useCommands, useRead, versionOf, type Row } from "./api";
import "../progress-foundation/progressFoundation.css";
import "./quality.css";

const labels: Record<string, string> = {
  scope: "Ámbito Quality",
  inherit_to_descendants: "Heredar a descendientes",
  effective_from: "Vigente desde ISO 8601",
  effective_to: "Vigente hasta ISO 8601",
  inspection_types: "Tipos de inspección",
  test_types: "Tipos de ensayo",
  control_point_types: "Tipos de punto de control",
  result_codes: "Resultados Quality",
  ncr_categories: "Categorías NCR",
  severities: "Severidades",
  dispositions: "Disposiciones",
  corrective_action_types: "Tipos de acción",
  punch_categories: "Categorías de deficiencia",
  acceptance_profiles: "Perfiles de aceptación",
  separation_of_duties: "Separación de funciones",
  approval_thresholds: "Umbrales de aprobación",
  checklist_templates: "Plantillas de checklist",
};
function ProfileEditor({
  content,
  record,
  busy,
  submit,
  token,
  revision,
}: {
  content: Row;
  record?: Row;
  busy: boolean;
  submit: (body: Row) => Promise<Row | null>;
  token: string;
  revision: number;
}) {
  const fields: FieldSpec[] = [
    ...(!record ? [{ key: "code", label: "Código del perfil Quality", required: true }] : []),
    { key: "name", label: "Nombre del perfil Quality", required: true, initial: text(record?.name) },
    ...Object.entries(content).map(
      ([key, value]): FieldSpec => ({
        key: `content_${key}`,
        label: labels[key] ?? key.replace(/_/g, " "),
        required: value !== null,
        kind:
          typeof value === "boolean"
            ? "boolean"
            : typeof value === "number"
              ? "integer"
              : Array.isArray(value) || isRow(value)
                ? "json"
                : undefined,
        initial:
          typeof value === "boolean"
            ? String(value)
            : Array.isArray(value) || isRow(value)
              ? JSON.stringify(value, null, 2)
              : text(value),
      })
    ),
  ];
  return (
    <FieldCommandForm
      label={record ? "Guardar borrador Quality" : "Crear borrador Quality"}
      spec={{ fields }}
      environment={{ token, base: profilesRoot, profile: content, revision }}
      busy={busy}
      submit={(body) => {
        const contentJson = { ...content };
        for (const key of Object.keys(content))
          contentJson[key] = body[`content_${key}`] ?? (content[key] === null ? null : content[key]);
        return submit({
          ...(record ? {} : { code: body.code }),
          name: body.name,
          content_json: contentJson,
          reason: body.reason,
        });
      }}
    />
  );
}
export default function QualityProfilesAdminView({ token }: { token: string }) {
  const commands = useCommands(token, profilesRoot);
  const result = useRead(token, profilesRoot, "", commands.revision);
  const [selected, setSelected] = useState("");
  const [editor, setEditor] = useState("");
  const record = rows(result.data).find((row) => text(row.id) === selected);
  const content = isRow(record?.content_json)
    ? record.content_json
    : isRow(result.data?.default_content)
      ? result.data.default_content
      : null;
  const status = text(record?.status).toUpperCase();
  const version = versionOf(record?.version);
  const canConfigure = permits(result.data?.allowed_actions, "admin.configure");
  const canPublish = permits(result.data?.allowed_actions, "admin.publish");
  const show = (row: Row | null) => {
    if (row?.id) {
      setSelected(text(row.id));
      setEditor("");
    }
    return row;
  };
  return (
    <section className="progressFoundation qualityManager" aria-label="Quality Management Profiles">
      <CompactModuleHeader
        title="Quality Management Profiles"
        eyebrow="ADMIN MODE · QUALITY · O3B"
        description="Catálogos, checklists, criterios y separación de funciones. Los perfiles publicados se corrigen mediante sucesor."
        tone="admin"
        metrics={[{ label: "Perfiles", value: rows(result.data).length }]}
        actions={
          <button type="button" onClick={commands.reload}>
            Actualizar perfiles Quality
          </button>
        }
      />
      <ReadState {...result} retry={commands.reload} />
      {commands.error ? (
        <p role="alert" className="progressError">
          {commands.error}
        </p>
      ) : null}
      {commands.message ? <p role="status">{commands.message}</p> : null}
      {result.data ? (
        <section className="progressPanel">
          <Records
            label="Perfiles Quality"
            items={rows(result.data)}
            columns={[
              ["id", "ID"],
              ["code", "Código"],
              ["name", "Nombre"],
              ["revision", "Revisión"],
              ["version", "Versión"],
              ["status", "Estado"],
            ]}
            select={show}
          />
          {canConfigure ? (
            <button
              type="button"
              onClick={() => {
                setSelected("");
                setEditor("create");
              }}
            >
              Nuevo perfil Quality
            </button>
          ) : null}
          {editor === "create" && canConfigure && content ? (
            <ProfileEditor
              key="new"
              content={content}
              busy={commands.busy || result.loading}
              token={token}
              revision={commands.revision}
              submit={async (body) => show(await commands.command("", body))}
            />
          ) : null}
          {record && content ? (
            <section className="qualityDetail" aria-label="Perfil Quality seleccionado">
              <h3>
                {text(record.name)} · {status}
              </h3>
              <Evidence title="Configuración Quality publicada y versionada" value={content} />
              {status === "DRAFT" && canConfigure && version ? (
                <ProfileEditor
                  key={`${selected}:${version}`}
                  record={record}
                  content={content}
                  busy={commands.busy || result.loading}
                  token={token}
                  revision={commands.revision}
                  submit={async (body) => show(await commands.command(`/${selected}`, body, version, "PUT"))}
                />
              ) : null}
              {status === "DRAFT" && canPublish && version ? (
                <button type="button" onClick={() => setEditor("publish")}>
                  Publicar perfil Quality…
                </button>
              ) : null}
              {status === "PUBLISHED" && canConfigure && version ? (
                <button type="button" onClick={() => setEditor("successor")}>
                  Crear sucesor Quality…
                </button>
              ) : null}
              {version &&
              ((editor === "publish" && status === "DRAFT" && canPublish) ||
                (editor === "successor" && status === "PUBLISHED" && canConfigure)) ? (
                <FieldCommandForm
                  label={editor === "publish" ? "Publicar perfil Quality" : "Crear sucesor Quality"}
                  spec={{}}
                  environment={{ token, base: profilesRoot, profile: content, revision: commands.revision }}
                  busy={commands.busy || result.loading}
                  submit={async (body) => show(await commands.command(`/${selected}/${editor}`, body, version))}
                />
              ) : null}
            </section>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
