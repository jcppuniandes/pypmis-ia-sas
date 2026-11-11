# Revisión técnica de alcance O2A

Revisión de código y evidencia realizada el 10 de noviembre de 2026.
No constituye aceptación de negocio, firma autorizada ni certificación
de seguridad o capacidad de producción.

- Ingeniería tiene tablas distintas para Deliverable, Revision, Review,
  ReviewComment, Release, DesignPackage, Interface, Mapping e History.
  `EngineeringDesignPackage` no usa la tabla `awp_work_packages` y no
  reemplaza `WorkPackage`. Los enlaces usan identificadores tipados.
- Liberar IFC escribe el hecho técnico, el historial y los recibos de
  comando existentes. No escribe Scope, P6, Cost, Progress ni Forecast.
  Los consumidores validan fuentes explícitas dentro de su propio comando.
- La migración 0076 añade protecciones de eliminación, inmutabilidad de
  releases, historial y mappings, revisiones terminales y perfiles publicados.
  Los triggers comprueban alcance, referencias, actores y snapshot de aprobación.
- La selección y el pin de CDE requieren vínculo operativo explícito,
  membresía legacy y autorización documental. Las vistas y replays redactan
  referencias que el actor actual no puede consultar.
- El cierre AWP usa un comando separado. Para `engineering:...` valida tipo
  de restricción, paquete y aplicabilidad, elegibilidad y hash actual, además
  de RBAC, ETag y separación de actores. No existe cierre automático.
- La revisión encontró un caso de entrada Unicode que podía provocar 500
  antes de consultar PostgreSQL. Se añadió validación ASCII con cuatro
  pruebas de rechazo. El cierre exige repetir la suite congelada después
  de este ajuste.
- No se identificaron defectos S1 o S2 en este perímetro. Los límites S3/S4
  se mantienen explícitos en el informe y su matriz, incluidos selectores
  acotados, etiquetas opcionales y falta de prueba de escala productiva.
- No se alteraron App.tsx, el visor IFC, modelos o esquemas globales ni
  migraciones anteriores; no se implementaron las autoridades O2B/O2C.

El dictamen de liberación depende también de la ejecución final PostgreSQL,
Chromium, frontend, preservación y controles nativos y visuales de los documentos.
