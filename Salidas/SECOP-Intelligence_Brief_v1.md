# SECOP Intelligence — Brief técnico

**Tema:** redes neuronales para experiencia de licitaciones, estabilidad del VPS y datos de aprendizaje
**Fecha:** 22/10/2026
**Base:** revisión técnica de Juan Carlos Peñaranda (22/10/2026, 8:02 a. m.)
**Alcance:** `secop-reader` (repositorio `multicompany-bid`)

---

## 1. Decisión central

Los modelos de embeddings **encuentran y ordenan** certificados candidatos. Las **reglas explícitas, con evidencia citada,** deciden si un certificado cumple.

Una similitud alta solo indica que el certificado parece relacionado con el requisito. No equivale a "cumple".

---

## 2. Estado actual

| Componente | Estado | Dato de la revisión |
|---|---|---|
| Red de embeddings | Integrada: IBM Granite Embedding 97M multilingüe (Apache 2.0) | Se usa para comparar **nombres de entidades contratantes**, no para evaluar certificados |
| Vectores en VPS | 163 vectores | Calculados hasta el 15/10/2026 |
| Desempeño Granite (uso actual) | Mejora la búsqueda; no sirve para decidir | AUC mediano 0,63 |
| Ranking adaptativo | No activo | 0 correcciones guardadas; 10 pares frente a un mínimo de 30 |
| Calibración de probabilidad | Sin feedback real | Lee todos los resultados sin filtrar por `company_key` |
| Tabla de feedback del ranking | Vacía | No tiene columna `company_key` |
| Modelo de regímenes | Mejor que la referencia original en el agregado | No supera el benchmark depurado; falla en espacio público |
| Navegador (Chromium) en VPS | Inestable | Procesos zombie y límite de PIDs |
| Memoria del VPS | Ajustada | La generación de vectores ya corre fuera del servidor |

Referencia de código: `secop_reader/dashboard_v3/services/experience_cierre_de_brecha_service.py:877`

---

## 3. Prioridades

### P1. Zombies de Chromium y límite de PIDs

**Por qué primero:** si el navegador no libera sus procesos, se cae la captura de datos de la que dependen las demás prioridades.

**Acciones**
1. Medir los procesos zombie y los PIDs en uso frente al límite del contenedor durante un ciclo completo de captura.
2. Identificar quién debe recoger los procesos hijo de Chromium. Hipótesis a verificar: el PID 1 del contenedor no los recoge. Si se confirma, ejecutar el contenedor con un proceso init (`init: true` en Docker Compose, o `tini`).
3. Revisar que cada navegador, contexto y página se cierre en un bloque `finally`, también cuando falla la captura.

**Restricción:** no aumentar la concurrencia del navegador hasta corregir la recolección de procesos.

**Criterio de salida:** el conteo de zombies vuelve a cero después de cada ciclo, y el número de PIDs se mantiene estable y por debajo del límite durante una jornada completa de captura.

---

### P2. Alcance multiempresa del aprendizaje

**Por qué ahora:** ambas tablas están vacías. Hoy no hay mezcla de datos entre empresas y el cambio de esquema no requiere migrar datos existentes. Después de alimentarlas, corregirlo sale más caro.

**Decisión requerida:** el aprendizaje será

- **Global:** un solo modelo con datos de todas las empresas.
- **Por cliente:** un modelo o una calibración por `company_key`.
- **Híbrido:** una base global y un ajuste por cliente cuando ese cliente tenga datos suficientes.

**Acciones, cualquiera que sea la decisión**
1. Agregar `company_key` a la tabla de feedback del ranking.
2. Hacer que la calibración filtre por `company_key`. Si se elige el modo global, documentar en el código que se omite el filtro a propósito.
3. Registrar en cada fila la versión del modelo que produjo la sugerencia.

---

### P3. Captura de feedback de analistas

**Problema:** el ranking adaptativo y la calibración no tienen datos reales con los que aprender.

**Acciones**
1. Guardar cada corrección de un analista con estos campos: requisito, certificado, decisión del analista, motivo, `company_key`, fecha y versión del modelo.
2. Alcanzar al menos los 30 pares que exige el umbral actual. Si en P2 se elige aprendizaje por cliente, el umbral debe contarse por cada empresa.
3. Usar estos mismos casos revisados como conjunto de evaluación de P5.

**Criterio de salida:** se alcanza el umbral y el ranking adaptativo se activa con datos reales.

---

### P4. Validación del modelo de regímenes por segmento y en el tiempo

**Problema:** el resultado agregado oculta fallas por segmento. El modelo no supera el benchmark depurado y falla en espacio público.

**Acciones**
1. Reportar las métricas por segmento, con espacio público como caso obligatorio.
2. Validar con cortes temporales (entrenar con el pasado y evaluar con el futuro), no con particiones aleatorias.
3. Comparar siempre contra el benchmark depurado, no contra la referencia original.
4. Definir el tratamiento de espacio público: excluirlo o usar el benchmark como respaldo en ese segmento.

**Regla de promoción:** el modelo no entra a producción mientras no supere el benchmark depurado en el agregado y en cada segmento crítico.

---

### P5. Embeddings para experiencia: Granite frente a BGE-M3

**Uso propuesto:** recuperar y ordenar los certificados candidatos para cada requisito del pliego.

| Modelo | Licencia | Rasgos relevantes |
|---|---|---|
| [IBM Granite Embedding 97M multilingüe](https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2) | Apache 2.0 | Ya integrado; liviano |
| [BAAI BGE-M3](https://huggingface.co/BAAI/bge-m3) | MIT | Multilingüe; vectores densos, coincidencia de términos y representación multivector; documentos de hasta 8.192 tokens |

**Protocolo de comparación**
1. Usar los casos revisados por analistas (P3).
2. Separar los casos de entrenamiento y de prueba **por empresa**, para que ninguna empresa aparezca en ambos.
3. Medir la recuperación con recall@k y nDCG@k: si los certificados válidos aparecen arriba en la lista.
4. Evaluar BGE-M3 solo con vectores densos y también combinado con coincidencia de términos.
5. Generar los vectores fuera del VPS. BGE-M3 es bastante más pesado que Granite, y la memoria del servidor no da margen.

**Restricción:** no entrenar un modelo propio antes de terminar esta comparación con datos revisados.

---

## 4. Flujo de decisión para experiencia

```text
Requisito del pliego
   -> Recuperación semántica (Granite o BGE-M3): top-k certificados candidatos
   -> Verificación por reglas:
        · valor en SMMLV
        · actividades
        · fechas
        · reglas específicas del pliego
   -> Evidencia citada (documento, página, campo)
   -> Veredicto: CUMPLE | NO CUMPLE | REVISIÓN HUMANA
```

El puntaje del modelo solo sirve para ordenar los candidatos. Ningún umbral de similitud produce un "CUMPLE" automático.

---

## 5. Decisiones pendientes

| # | Decisión | Opciones | Bloquea |
|---|---|---|---|
| 1 | Alcance del aprendizaje | Global / por cliente / híbrido | P2, P3 |
| 2 | Umbral de pares | 30 en total / 30 por empresa | P3 |
| 3 | Tratamiento de espacio público | Excluir / usar el benchmark como respaldo | P4 |
| 4 | Dónde se generan los vectores | Equipo local / proceso por lotes externo | P5 |

---

## 6. Fuera de alcance por ahora

- Aumentar la concurrencia del navegador.
- Generar vectores en el VPS.
- Entrenar un modelo propio.
- Usar la similitud semántica como veredicto de cumplimiento.
