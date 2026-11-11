import { useState } from "react";
import { items, optionalId, recordId, text, versionOf } from "./api";
import { Input, Notes, ReadState, Reason, Records, Select, SubmitForm } from "./controls";
import { useEngineeringData } from "./hooks";
import { MappingsPanel } from "./MappingsPanel";
import type { EngineeringPanel } from "./types";

export function DesignGroupsPanel(scope: EngineeringPanel) {
  const groups = useEngineeringData(scope.token, scope.base, "/design-packages", scope.refreshKey);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [reason, setReason] = useState("");
  const [selected, setSelected] = useState("");
  const records = items(groups.value);
  const group = records.find((row) => recordId(row) === selected);
  async function create() {
    if (!scope.can("design_package.manage")) return;
    const row = await scope.command("/design-packages", {
      code: code.trim(),
      title: title.trim(),
      description: description.trim(),
      reason: reason.trim(),
    });
    if (row) {
      setSelected(recordId(row));
      setCode("");
      setTitle("");
      setDescription("");
      setReason("");
    }
  }
  return (
    <>
      <section className="progressPanel" aria-label="Engineering Groups">
        <h3>Engineering Groups</h3>
        <p>Un grupo técnico ordena entregables. No es un EWP; vincularlo a un EWP no cambia AWP.</p>
        <ReadState {...groups} reload={scope.reload} />
        {groups.value ? (
          <Records
            label="Grupos de diseño"
            items={records}
            columns={[
              ["code", "Código"],
              ["title", "Grupo"],
              ["description", "Descripción"],
              ["status", "Estado"],
            ]}
            select={(row) => setSelected(recordId(row))}
          />
        ) : null}
        {scope.can("design_package.manage") ? (
          <SubmitForm onSubmit={create} disabled={scope.busy}>
            <Input label="Código de grupo de diseño" value={code} onChange={setCode} required />
            <Input label="Título de grupo de diseño" value={title} onChange={setTitle} required />
            <Notes label="Descripción de grupo de diseño" value={description} onChange={setDescription} />
            <Reason label="Motivo de grupo de diseño" value={reason} onChange={setReason} />
            <button type="submit">Crear grupo de diseño</button>
          </SubmitForm>
        ) : null}
      </section>
      {group ? <MappingsPanel key={selected} scope={scope} parent={group} mode="design-packages" editable /> : null}
    </>
  );
}

export function InterfacesPanel(scope: EngineeringPanel) {
  const interfaces = useEngineeringData(scope.token, scope.base, "/interfaces", scope.refreshKey);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [type, setType] = useState("DISCIPLINE");
  const [source, setSource] = useState("");
  const [reason, setReason] = useState("");
  const [selected, setSelected] = useState("");
  const [action, setAction] = useState("");
  const [resolution, setResolution] = useState("");
  const [transitionReason, setTransitionReason] = useState("");
  const records = items(interfaces.value);
  const chosen = records.find((row) => recordId(row) === selected);
  const status = text(chosen?.status).toUpperCase();
  const version = versionOf(chosen);
  const editable = scope.can("interface.manage");
  const actions = status === "OPEN" ? ["resolve", "cancel"] : status === "RESOLVED" ? ["close"] : [];
  async function create() {
    if (!editable) return;
    const row = await scope.command("/interfaces", {
      code: code.trim(),
      title: title.trim(),
      interface_type: type,
      deliverable_id: optionalId(recordId(scope.deliverable)),
      source_reference: source.trim(),
      reason: reason.trim(),
    });
    if (row) {
      setSelected(recordId(row));
      setCode("");
      setTitle("");
      setSource("");
      setReason("");
    }
  }
  async function transition() {
    if (!editable || !chosen || version === undefined || !actions.includes(action)) return;
    const row = await scope.command(
      `/interfaces/${selected}/transition`,
      {
        action,
        resolution: resolution.trim() || null,
        reason: transitionReason.trim(),
      },
      version
    );
    if (row) {
      setResolution("");
      setTransitionReason("");
      setAction("");
    }
  }
  return (
    <section className="progressPanel" aria-label="Interfaces">
      <h3>Interfaces</h3>
      <p>
        Registro mínimo de dependencias de Ingeniería. Una referencia RFI/TQ no crea otro expediente ni cambia su
        autoridad.
      </p>
      <ReadState {...interfaces} reload={scope.reload} />
      {interfaces.value ? (
        <Records
          label="Interfaces Engineering"
          items={records}
          columns={[
            ["code", "Código"],
            ["title", "Interfaz"],
            ["interface_type", "Tipo"],
            ["deliverable_id", "Entregable"],
            ["source_reference", "Referencia"],
            ["status", "Estado"],
            ["resolution", "Resolución"],
          ]}
          select={(row) => {
            setSelected(recordId(row));
            setAction("");
          }}
        />
      ) : null}
      {editable ? (
        <SubmitForm onSubmit={create} disabled={scope.busy}>
          <Input label="Código de interfaz" value={code} onChange={setCode} required />
          <Input label="Título de interfaz" value={title} onChange={setTitle} required />
          <Select
            label="Tipo de interfaz"
            value={type}
            onChange={setType}
            values={["DISCIPLINE", "PROCUREMENT", "CONSTRUCTION", "VENDOR", "OWNER"]}
            required
          />
          <Input label="Referencia RFI/TQ o interfaz" value={source} onChange={setSource} />
          <Reason label="Motivo de interfaz" value={reason} onChange={setReason} />
          <button type="submit">Registrar interfaz</button>
        </SubmitForm>
      ) : null}
      {editable && chosen && actions.length && version !== undefined ? (
        <SubmitForm onSubmit={transition} disabled={scope.busy}>
          <Select label="Acción sobre interfaz" value={action} onChange={setAction} values={actions} required />
          {action === "resolve" ? (
            <Notes label="Resolución de interfaz" value={resolution} onChange={setResolution} required />
          ) : null}
          <Reason label="Motivo de transición de interfaz" value={transitionReason} onChange={setTransitionReason} />
          <button type="submit">Registrar transición de interfaz</button>
        </SubmitForm>
      ) : null}
    </section>
  );
}
