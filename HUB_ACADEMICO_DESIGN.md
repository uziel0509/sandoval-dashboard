# Diseño de Arquitectura: Hub Académico Inteligente
**Versión:** 1.0  
**Fecha:** 2026-02-13  
**Autor:** Ingeniero de Software Senior & Experto en IA Educativa

## 1. Visión General
El **Hub Académico Inteligente** es una plataforma móvil centralizada diseñada para estudiantes universitarios que automatiza la gestión académica y potencia el aprendizaje mediante IA avanzada. 

## 2. Pila Tecnológica Sugerida (Tech Stack)

Para garantizar escalabilidad, rendimiento en móviles y capacidades avanzadas de IA, se recomienda la siguiente arquitectura moderna:

*   **Frontend (Móvil):** **Flutter** (Dart).
    *   *Por qué:* Permite desplegar en iOS y Android con un solo código base, excelente rendimiento nativo y acceso robusto a hardware (cámara para escanear).
*   **Backend & API:** **FastAPI** (Python).
    *   *Por qué:* Python es el lenguaje nativo de la IA y el análisis de datos. Necesario para integrar librerías como `Matplotlib`/`Plotly` y orquestar llamadas complejas a LLMs.
*   **Base de Datos:** **Firebase** (Firestore & Auth).
    *   *Por qué:* Sincronización en tiempo real, autenticación sencilla y manejo eficiente de datos no estructurados (JSON de cursos, horarios).
*   **Almacenamiento:** **Google Cloud Storage** (o Firebase Storage).
    *   *Por qué:* Para guardar imágenes de ejercicios, PDFs de sílabos y los reportes generados.
*   **Motor de IA:** **Google Gemini 1.5 Pro** (vía Vertex AI o Google AI Studio).
    *   *Por qué:* Ventana de contexto masiva (ideal para libros/sílabos enteros) y capacidad multimodal nativa (entiende imágenes de gráficos y manuscritos mejor que nadie).
*   **Integración Externa:** **Google Drive API** + **Google Calendar API**.
    *   *Por qué:* Calendario para recordatorios y Drive como "puente" transparente hacia NotebookLM.

---

## 3. Arquitectura del Sistema

### Diagrama Lógico de Flujo

```mermaid
graph TD
    User[Estudiante] -->|Sube Foto/PDF| App[App Móvil (Flutter)]
    App -->|Auth & Data| Firebase[Firebase (Auth/DB)]
    App -->|Archivos| Storage[Cloud Storage]
    App -->|Solicitud Procesamiento| Backend[Backend (FastAPI/Python)]
    
    subgraph "Núcleo de Inteligencia (Backend)"
        Backend -->|OCR & Razonamiento| Gemini[Gemini 1.5 Pro API]
        Backend -->|Generación Gráficos| Plotly[Matplotlib/Plotly]
        Backend -->|Generación PDF| ReportLab[ReportLab/WeasyPrint]
    end
    
    subgraph "Ecosistema Google"
        Backend -->|Crear Eventos| GCal[Google Calendar]
        Backend -->|Guardar Resúmenes| GDrive[Google Drive]
        GDrive -->|Fuente de Datos| NotebookLM[NotebookLM]
    end
    
    NotebookLM -->|Genera| Slides[Presentaciones/Diapositivas]
```

### Módulos Principales

1.  **Gestor de Horarios e Ingesta (The Organizer)**:
    *   **Input:** Fotos de horarios, PDFs de sílabos.
    *   **Proceso:** Gemini Vision extrae fechas, temas y bibliografía.
    *   **Output:** Estructura JSON de "Asignaturas", creación de carpetas en Drive, eventos en Google Calendar.

2.  **Solucionador Técnico (The Solver)**:
    *   **Input:** Foto del ejercicio.
    *   **Proceso:**
        1.  Gemini transcribe el problema a LaTeX/Texto.
        2.  Gemini razona la solución paso a paso.
        3.  Backend ejecuta código Python si se requieren gráficos precisos (ej. graficar función).
        4.  Generación de PDF con reporte técnico.
    *   **Output:** PDF descargable "Informe Técnico".

3.  **Conector NotebookLM (The Summarizer)**:
    *   **Proceso:** Periódicamente o bajo demanda, el sistema toma notas/materiales, genera un "Resumen Estructurado" (Markdown) y lo sube a una carpeta específica en Drive vinculada a un cuaderno de NotebookLM.

---

## 4. Módulo de Experiencia Estudiantil Avanzada (Smart Study OS)

Para combatir la sensación de "pobreza" funcional y crear una experiencia premium, se integran los siguientes módulos de vida universitaria:

### 4.1. The "Focus Zone" (Productividad & Bienestar)
*   **Pomodoro Conectado:** Temporizador sincronizado con bloqueo de notificaciones (modo "No Molestar" del móvil).
*   **Ambient Mode:** Reproductor integrado de Lo-Fi Beats / Ruido Blanco / Sonidos de Cafetería para concentración profunda.
*   **Estado de Ánimo Académico:** Check-in diario de estrés y energía. La IA sugiere pausas o cambios de materia según el estado.

### 4.2. Gamificación Académica (Level Up)
*   **Sistema de XP:** Ganar experiencia por:
    *   Completar tareas a tiempo (+100 XP).
    *   Sesiones de estudio sin distracciones (+50 XP/hora).
    *   Racha de días consecutivos (+20 XP).
*   **Logros Desbloqueables:** "Café Infinito" (Estudiar >4h seguidas), "Bibliotecario" (Subir >10 PDFs).
*   **Tablas de Clasificación:** Comparar horas de estudio con amigos (opcional).

### 4.3. Herramientas de "Super Estudiante"
*   **Simulador de Exámenes (Quiz Master):**
    *   Genera un examen de prueba basado en *todos* los documentos subidos de una materia.
    *   Modo "Muerte Súbita": 5 preguntas difíciles, si fallas una, pierdes la racha.
*   **Flashcards Automáticas:** La IA detecta definiciones clave en los textos y crea mazos de repaso automáticamente.
*   **Resúmenes de Voz (Podcast Mode):** Convierte los resúmenes de texto a audio para escuchar camino a la universidad.
*   **Generador de Memes de Estudio:** Alivio cómico. Genera memes relacionables sobre el tema que estás sufriendo (ej: "Yo intentando entender Termodinámica a las 3AM").

### 4.4. Dashboard Financiero "Estudiante Fau"
*   **Control de Gastos Simple:** Categorías predefinidas (Comida, Fotocopias, Transporte, Fiestas).
*   **Meta de Ahorro:** "Para el viaje de graduación" o "Nueva Laptop".

---

## 4. Prompt del Sistema (System Prompt) - Módulo "The Solver"

Este es el prompt que el backend enviará a Gemini para actuar como tutor experto.

**Rol:** Eres un Profesor Catedrático de Ingeniería y Ciencias Exactas con 20 años de experiencia, reconocido por tu claridad pedagógica y rigor técnico.

**Objetivo:** Recibirás una imagen de un problema (Matemáticas, Física, Química o Ingeniería). Debes generar un **Informe Técnico de Solución** detallado.

**Formato de Salida (JSON estructurado para el Backend):**
Debes responder *únicamente* en formato JSON con la siguiente estructura:

```json
{
  "titulo": "Título descriptivo del problema",
  "materia": "Cálculo Multivariable / Física Mecánica / etc.",
  "dificultad": "Intermedia/Avanzada",
  "transcripcion_latex": "El texto del problema en LaTeX...",
  "pasos_solucion": [
    {
      "paso": 1,
      "titulo": "Planteamiento Teórico",
      "descripcion": "Explicación conceptual de qué leyes o teoremas aplican...",
      "formulas": "Ecuaciones en LaTeX"
    },
    {
      "paso": 2,
      "titulo": "Desarrollo Matemático",
      "descripcion": "Resolución paso a paso...",
      "formulas": "..."
    }
  ],
  "codigo_grafica_python": "Código Python (usando Matplotlib) para generar la gráfica representativa de la solución. DEBE ser código ejecutable y autónomo.",
  "resultado_final": "El valor o expresión final.",
  "verificacion": "Breve análisis dimensional o comprobación lógica del resultado.",
  "sugerencia_slides": "Punto clave para incluir en una presentación de NotebookLM."
}
```

**Instrucciones de Comportamiento:**
1.  **Analiza la imagen.** Si es ilegible, solicita una nueva toma.
2.  **Rigor:** No omitas pasos algebraicos intermedios complejos.
3.  **Pedagogía:** Explica el *porqué* de cada paso, no solo el *cómo*.
4.  **Visualización:** Si el problema implica funciones, vectores o geometría, SIEMPRE genera el código Python para visualizarlo.

---

## 5. Guía de Integración con NotebookLM

NotebookLM no tiene una API pública directa de escritura (aún), pero se integra nativamente con **Google Drive**. "Hackearemos" este flujo para automatizar la creación de diapositivas.

**Paso 1: Estructura en Google Drive**
La App creará automáticamente (usando la API de Drive) la siguiente estructura:
`/Hub_Academico_Data/`
  `|_ Física_1/`
      `|_ Syllabus.pdf`
      `|_ Apuntes_Clase_1.md`
      `|_ Resumen_Semana_1.md`

**Paso 2: El "Resumen Estructurado" (Secret Sauce)**
Para que NotebookLM genere buenas diapositivas, no le des texto plano. La App generará archivos `.md` (Markdown) con esta estructura específica:

```markdown
# Resumen Ejecutivo: [Tema]
## Conceptos Clave
- [Concepto A]: Definición simple.
- [Concepto B]: Definición simple.

## Narrativa para Presentación
1. **Diapositiva 1 (Intro):** [Texto sugerido para el orador]
2. **Diapositiva 2 (Desarrollo):** [Puntos bala]
3. **Diapositiva 3 (Conclusión):** [Idea fuerza]
```

**Paso 3: Flujo de Usuario**
1.  El estudiante escanea sus apuntes o sube el PDF del tema.
2.  La IA de la App (Backend) procesa el contenido, extrae lo importante y crea el archivo `Resumen_Semana_X.md` en la carpeta de Drive.
3.  El usuario abre **NotebookLM**, selecciona la carpeta de Drive como "Fuente".
4.  El usuario escribe en el chat de NotebookLM: *"Genera una presentación basada en la fuente Resumen_Semana_X"*.
5.  NotebookLM entregará el guion y los puntos clave listos para copiar a PowerPoint/Slides.
