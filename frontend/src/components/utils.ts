export function currency(value: number, code: string) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: code, maximumFractionDigits: 0 }).format(value);
}

export function fileSize(value: number) {
  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (value >= 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${value} B`;
}

export function sourceLabel(source?: string) {
  const labels: Record<string, string> = {
    p6_xer: "Schedule XER",
    p6_xml: "Schedule XML",
    ms_project_xml: "Schedule XML",
    ms_project_mpp: "Schedule file",
  };
  return source ? (labels[source] ?? source) : "Not imported";
}

export function statusLabel(status?: string) {
  if (!status) {
    return "";
  }
  return status.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function neutralScheduleText(value: string) {
  return value
    .replace(/Schedule file received from Primavera P6 or MS Project\./gi, "Source schedule file received.")
    .replace(/Primavera P6 or MS Project/gi, "source schedule")
    .replace(/MSPROJECT_WORKFLOW_TRIGGER/gi, "Schedule Baseline Intake")
    .replace(/SCHEDULE_WORKFLOW_TRIGGER/gi, "Schedule Baseline Intake")
    .replace(/MSPROJECT/gi, "SCHEDULE")
    .replace(/MS Project/gi, "schedule")
    .replace(/Imported_Schedule_/gi, "Imported Schedule ")
    .replace(/Imported Schedule_/gi, "Imported Schedule ")
    .replace(/SCHEDULE_XML_IMPORT/gi, "Imported Schedule")
    .replace(/P6\/MSP/gi, "source schedule")
    .replace(/\bMSP\b/gi, "schedule")
    .replace(/Imported\W+Schedule[_\s-]*/gi, "Imported Schedule ")
    .replace(/CONTROL\W+BASELINE[_\s-]*/gi, "Control Baseline ");
}
