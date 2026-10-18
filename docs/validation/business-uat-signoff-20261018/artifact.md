# Contrato de documentos de aceptación empresarial

## Referencia retenida

Referencia absoluta: `C:/Users/Ricardo/Documents/GitHub/pypmis-ia-sas/outputs/gate07j-controlled-class-b-20261016/P&Pmis_Strategic_Macroprocess_Final_Release_Closeout.docx`.
SHA256: `2a0c470c57b833b89c85758863653afa04a03b941481e18ee37aabcdfc76d031`.
11 páginas, una sección. Se revisaron visualmente las11 imágenes existentes verificables en `outputs/.qa/gate07j-controlled-class-b-rebuild/word-closeout/pages-final/page-1.png` a `page-11.png`. No se presupone que los nuevos documentos tengan11 páginas.

La referencia y los otros5documentos obligatorios permanecen byte-idénticos. Los nuevos Word parten del paquete retenido, no de un documento vacío ni de una plantilla genérica. El builder compara todos los19partes del ZIP, preservando byte por byte las17partes distintas de `word/document.xml` y `word/footer1.xml`.

## Página y mobiliario

Letter portrait8.5x11in, una sección. Width7772400EMUs; height10058400. Márgenes top/bottom/left/right658495EMUs (0.7201in). Header274320EMUs(0.3in), footer320040EMUs(0.35in). Sin primera página distinta, sin columnas especiales. Se conserva sectPr exacto. Logo de la primera línea se clona intacto con relación al mismo image1.png y alt `Logotipo de P&Pmis Construction AI`.

Footer existente alineado derecha con fecha literal16octubre2026 y campo PAGE. Única alteración permitida del footer: fecha de emisión18octubre2026. Campo PAGE, estilos, relaciones y geometría se conservan. No se agrega TOC ni referencias de página no verificadas.

## Tipografía fuente

Normal Aptos11pt #202A33, after5pt, line1.070833. Title Aptos24pt black, before0/after5pt, line1. Subtitle Aptos12pt black. Heading1 Aptos15pt black,before10/after5pt; Heading2 Aptos12pt black,before10/after5pt. Sin reglas decorativas. Títulos y encabezados nuevos solo palabras/números/espacios; IDs de dominio se mantienen en texto de cuerpo cuando incluyen signos.

Las tablas reutilizan tblPr y tcPr fuente: layoutfixed; bordes D9D9D9 single5; headerfill17324D con Aptos9.5pt blanco/negrita; body9.5pt202A33 y bandas blanco/F3F6F8 similares al patrón fuente. Padding100twips cada lado; valigncenter. Anchos deliberados por columna. Repetir header en páginas consecutivas. Filas expandibles, no altura exacta; no partir cada registro de formulario. No reducir bodygeneral11pt para forzar paginación.

## Slots y flujo permitido

`word/document.xml/w:document/w:body`: sustituir el contenido técnico previo por contenido de los dos nuevos documentos, conservando el párrafo inicial real de logo y sectPr. Se permiten párrafos/clones de estilos fuente, tablas/clones de propiedades fuente y saltos de página explícitos para formularios.

Documento de aceptación: portada/resumen, paquete A-L (mapa35actividades, matrizADMIN/USER,3rutas, Gate19requeridas15VALID4MISSING más1opcionalC), hallazgos6más2observaciones, documentación y addendum de vigencia,15formulariosuna página por área con12campos de captura, registros de condiciones y rechazos vacíos y decisión final pendiente.

Informe técnico: hechos auditados actuales18Oct separados de evidencia técnica16/14, commitactual6672fd5 vs referenciainicial10a2442, integridad de código/evidencias, sin nuevas funciones, migraciones, pruebas ni DBwrites. No se transfiere el estado histórico de runtime a una validación viva nueva.

Cada formulario preserva vacíos: representante, cargo,organización, autoridad,fecha,decisión,condiciones,comentarios,evidenciarevisada,aprobación,propietarioyplazo. IDs y evidencia propuesta sí pueden prellenarse. No marcar casillas ACCEPT, MISSING reconocido ni documentación aceptada.

## Fidelidad y QA

Inventario de todas laspartes y hashes de referencia y salidas se genera en el manifiesto de construcción. Fallar si cualquier preserve-only part cambia odesaparece. Verificar documento6fuentes conSHAcontrolados. SourceStyle/sect/logo/relaciones conservados; fechafooterúnicaexcepción.

Root realiza exportación Word oculta read-only a PDF temporal y usa el renderer canónico empaquetado con puente existente, sin usar LibreOffice delusuario ni editar dependencias. Renderizar y revisar todas las páginas finales; corregir y repetir. Las fuentes retenidas nunca se guardan desde Word. El manifiesto del builder no sustituye la revisión visual.
