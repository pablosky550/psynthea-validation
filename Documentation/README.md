# Validación Científica de Psynthea frente a Synthea

> **Entrega Final del Proyecto**  
> Instituto Ramón y Cajal de Investigación Sanitaria (IRYCIS)

---

## Información general

| Campo | Valor |
|--------|-------|
| Proyecto | Validación Científica de Psynthea frente a Synthea |
| Institución | Instituto Ramón y Cajal de Investigación Sanitaria (IRYCIS) |
| Tipo de entrega | Memoria técnica y evidencias finales |
| Autor | Pablo García Tello |
| Fecha | Agosto 2026 |
| Versión | 1.0 |

---

# Resumen ejecutivo

Esta entrega recoge el trabajo desarrollado durante el proyecto de **Validación Científica de Psynthea frente a Synthea**, realizado en el Instituto Ramón y Cajal de Investigación Sanitaria (IRYCIS).

El objetivo del proyecto ha sido desarrollar una metodología reproducible que permitiera evaluar objetivamente el grado de equivalencia entre **Psynthea**, una reimplementación en Python del simulador clínico Synthea, y el simulador original **Synthea**.

Para ello se diseñó un pipeline completo de validación capaz de ejecutar ambos simuladores bajo condiciones experimentales equivalentes, comparar automáticamente los resultados generados, identificar discrepancias funcionales, realizar análisis estadísticos, generar interpretación clínica y documentar las posibles causas raíz de las diferencias observadas.

Paralelamente, las discrepancias detectadas sirvieron como base para implementar mejoras directamente sobre Psynthea. Cada modificación fue posteriormente reevaluada mediante nuevas campañas experimentales con el objetivo de cuantificar de forma objetiva su impacto sobre el comportamiento del simulador.

Como resultado, esta entrega documenta tanto la metodología desarrollada como las modificaciones implementadas, las campañas ejecutadas y las evidencias que respaldan las conclusiones obtenidas.

---

# Estado final del proyecto

| Área | Estado |
|------|:------:|
| Pipeline de validación científica | ✅ Completado |
| Automatización de campañas | ✅ Completada |
| Comparación funcional Synthea vs Psynthea | ✅ Implementada |
| Comparación estadística | ✅ Implementada |
| Interpretación clínica | ✅ Implementada |
| Análisis de causa raíz | ✅ Implementado |
| Mejoras sobre Psynthea | ✅ Implementadas y reevaluadas |
| Evidencias reproducibles | ✅ Incluidas |
| Equivalencia científica global | ⚠️ No demostrada |
| Uso como sustituto general de Synthea en investigación | ⚠️ Requiere validación adicional |

> **Conclusión ejecutiva**
>
> El proyecto demuestra una mejora significativa del comportamiento funcional de Psynthea y proporciona una infraestructura reproducible para continuar su validación. Sin embargo, las evidencias obtenidas no permiten afirmar todavía una equivalencia científica completa respecto a Synthea para todos los escenarios de investigación.

---

# Objetivos alcanzados

Durante el proyecto se desarrollaron las siguientes líneas principales de trabajo:

- Diseño e implementación de un pipeline reproducible para la validación científica entre Synthea y Psynthea.
- Desarrollo de campañas experimentales progresivas (p10, p100 y p1000).
- Comparación funcional de entidades clínicas generadas por ambos simuladores.
- Incorporación de análisis estadísticos y métricas de similitud.
- Generación automática de informes científicos reproducibles.
- Implementación de interpretación clínica y análisis de causa raíz.
- Identificación objetiva de discrepancias funcionales.
- Implementación y reevaluación de mejoras sobre Psynthea.
- Organización de las evidencias generadas durante el proyecto.

---

# Resumen metodológico

El proyecto siguió un proceso iterativo basado en evidencia.

```text
Configuración experimental armonizada
                │
                ▼
 Generación de cohortes equivalentes
                │
                ▼
 Ejecución de Synthea y Psynthea
                │
                ▼
 Comparación funcional
                │
                ▼
 Comparación estadística
                │
                ▼
 Interpretación clínica
                │
                ▼
 Análisis de causa raíz
                │
                ▼
 Implementación de mejoras
                │
                ▼
 Nueva validación
```

Cada modificación implementada fue validada nuevamente utilizando exactamente la misma metodología experimental.

---

# Principales aportaciones

Las contribuciones realizadas durante el proyecto pueden agruparse en cuatro bloques.

## 1. Infraestructura de validación

Se desarrolló un pipeline reproducible capaz de:

- ejecutar campañas experimentales;
- comparar automáticamente ambos simuladores;
- generar informes científicos;
- identificar discrepancias;
- documentar resultados de forma reproducible.

---

## 2. Mejoras implementadas sobre Psynthea

Las campañas de validación permitieron identificar e implementar mejoras relacionadas con:

- generación demográfica;
- compatibilidad con el Generic Module Framework;
- Keystone;
- ciclo de vida de condiciones;
- semántica temporal de `PriorState.within`;
- recurrencia de revisiones preventivas (`wellness_encounters`);
- ampliación de la batería de pruebas automatizadas.

Todas estas modificaciones fueron posteriormente reevaluadas mediante nuevas campañas experimentales.

---

## 3. Validación científica

Se ejecutaron campañas progresivas que permitieron:

- caracterizar el comportamiento funcional del simulador;
- localizar discrepancias reales;
- medir objetivamente el efecto de las mejoras implementadas;
- identificar limitaciones todavía existentes.

---

## 4. Evidencias reproducibles

Toda la información presentada en esta entrega queda respaldada mediante:

- informes científicos (`scientific_report`);
- resultados agregados de campañas;
- resultados funcionales;
- análisis estadísticos;
- interpretación clínica;
- análisis de causa raíz;
- artefactos generados automáticamente por el pipeline.

---

# Contenido de la entrega

La documentación incluida se encuentra organizada de la siguiente forma.

| Documento | Descripción |
|------------|-------------|
| **README.md** | Presentación general del proyecto y guía de la entrega. |
| **01_Resumen_Ejecutivo.pdf** | Resumen ejecutivo del trabajo realizado y de sus principales resultados. |
| **02_Memoria_Tecnica_Validacion.pdf** | Descripción completa del proyecto, metodología, modificaciones implementadas y resultados. |
| **03_Evidencias/** | Informes científicos y resultados principales del pipeline de validación. |
| **04_Artefactos/** | Informes HTML, JSON, CSV y demás resultados experimentales. |
| **05_Anexos/** | Información complementaria utilizada durante el proyecto. |

---

# Orden recomendado de revisión

Para facilitar la revisión técnica se recomienda seguir el siguiente orden:

1. README.md
2. 01_Resumen_Ejecutivo.pdf
3. 02_Memoria_Tecnica_Validacion.pdf
4. 03_Evidencias
5. 04_Artefactos
6. 05_Anexos

---

# Consideraciones finales

El propósito de este proyecto no ha sido demostrar una equivalencia absoluta entre Psynthea y Synthea, sino desarrollar una metodología objetiva que permita evaluar dicha equivalencia, identificar discrepancias reales, implementar mejoras sobre Psynthea y medir rigurosamente el impacto de cada modificación.

La principal aportación del trabajo no reside únicamente en las mejoras incorporadas al simulador, sino en la disponibilidad de una infraestructura de validación reproducible que permitirá continuar evaluando futuras versiones de Psynthea utilizando un procedimiento sistemático, trazable y basado en evidencia.

---

<div align="center">

**Instituto Ramón y Cajal de Investigación Sanitaria (IRYCIS)**

**Proyecto de Validación Científica de Psynthea frente a Synthea**

**Entrega Final de Prácticas**

</div>