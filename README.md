# SIGIN · Aula de aprendizaje práctico

Tres materias y 48 semanas: Alfabetización y Competencias Informacionales (GIG-502), Comercio Exterior (CEX-103-AC) y Gobierno Electrónico y Administración Pública (GIG-406). Hay 240 retos de práctica en el sitio y otros 240 retos de evaluación, organizados en 48 bancos privados de Supabase. Los títulos semanales proceden del HTML y los dos sílabos proporcionados. Las actividades desarrollan la teoría y los modelos de cada tema mediante conceptos clave, un caso breve y una tarea explícita. Los casos son simulaciones educativas; las referencias identifican autores, secciones y la utilidad de cada lectura.

## Desarrollo

Node.js >=22.18 y Python 3. Sin instalación npm ni dependencias de CDN durante el uso.

```sh
npm test
npm run build
npm start
```

`npm start` sirve el checkout en el puerto 4173. Las tareas cloud ya están aisladas; usar este checkout, no crear worktrees. Playwright/Chromium permiten ejecutar `python scripts/browser_smoke.py` cuando estén instalados. `SIGIN_TEST_URL` ajusta la dirección local del runner. `python3 scripts/background_smoke.py` verifica movimiento real, pausa, temas, limpieza al navegar y respaldo sin WebGL; las pruebas de interfaz usan movimiento reducido para capturas estables. `python3 scripts/motion_smoke.py` comprueba ausencia de rastro del cursor, destellos, atracción magnética, navegación y barra lateral con fixtures locales, teclado y pantalla táctil.

## Experiencia

- Diseño minimalista con portada tipográfica y paleta burdeos, crema, marrón, arena y coral, adaptada a los modos claro y oscuro. Escritorio con navegación lateral y contenido que aprovecha el ancho; móvil con menú y tarjetas apiladas.
- Fondo animado Gradient Waves de React Bits con olas visibles y superficies de lectura sólidas en la portada, con horizonte `#A60321` y escala `0.77`, adaptado a la paleta de ambos temas. Incluye pausa, movimiento reducido y fondo estático si WebGL no está disponible; sin peticiones a CDN. Licencia y atribución en `assets/vendor/licenses/react-bits.md`.
- Configuración de apariencia clara, oscura o del sistema, conservada en el navegador antes y después de iniciar sesión.
- Cursor estándar sin rastro, destellos al pulsar botones, atracción magnética limitada al contenido de las acciones y entradas verticales escalonadas al navegar. La barra lateral conserva sus opciones, foco y controles de teclado con efecto pop. Adaptaciones locales de ClickSpark, Magnet, AnimatedContent y AnimatedList de React Bits, sin React/GSAP ni CDN. El control de pausa detiene todos los efectos; la preferencia de movimiento reducido los desactiva. El magnetismo se aplica solo con ratón; en táctil se conservan los destellos al tocar.
- Materias separadas; semanas agrupadas por unidad. **Práctica y examen** permite elegir modalidad, materia y semana directamente. La práctica es libre; el examen respeta matrícula, calendario e intentos.
- La práctica marca cada respuesta correcta en verde y cada incorrecta en rojo, con etiquetas de texto. Al editar se retira la corrección anterior. El examen muestra su caso y consignas sin lecturas, conceptos de apoyo ni pistas; la corrección aparece después de entregar.
- El alta manual y Excel muestran validación, guardado pendiente y resultados persistentes. La confirmación consulta perfiles y matrículas en Supabase; no se agregan filas optimistas. La cédula genera automáticamente el identificador interno de Auth, y repetir una matrícula existente no crea otra cuenta ni cambia su contraseña.
- Cinco preguntas por semana: dos decisiones razonadas, relaciones de conceptos, una secuencia justificada y un crucigrama. Las actividades incluidas no exigen cálculos. Cada respuesta recibe una explicación y los casos contienen la información necesaria para resolverlos.
- Lecturas complementarias con enlace a un documento o apartado concreto, autor, sección sugerida y propósito de lectura.
- Panel docente: horarios de Ecuador, límite de intentos, autor de evaluaciones privadas de cuatro formatos, estudiantes manuales/Excel con vista previa, exportación y ajuste de notas con motivo.
- La vista previa usa un visitante ficticio y almacenamiento local. No hay identidades reales ni contraseñas precargadas en el código público.

## Supabase y estado real

La URL y clave publicable del proyecto están en `assets/config.js`. Supabase está activo: esquema aplicado, cuenta docente y único estudiante de prueba creados, este último matriculado en las tres materias. La función de altas está desplegada y sus permisos se comprobaron con sesiones reales. Auth usa la dirección académica final y tiene el registro público desactivado. Las altas exigen cambiar la clave temporal antes de cargar el aula; el usuario de prueba ya realizó ese cambio y la base de datos registró que dejó de usar la clave temporal. Ver [docs/SUPABASE.md](docs/SUPABASE.md).

La entrada pública de vista previa está desactivada. Para usar el aula es obligatorio iniciar sesión con una cuenta válida. La vista previa se habilita únicamente dentro de las pruebas de navegador con configuración simulada. Los contenidos estáticos son públicos; los datos personales y notas se guardan en Supabase con RLS. Los ejemplos de práctica tienen respuestas públicas para aprender. Las evaluaciones reales se crean aparte con el autor docente y se guardan en el esquema privado. Nunca cargar los mismos ejercicios públicos como evaluación secreta.

Cuenta estudiantil: correo `e{cedula}@live.uleam.edu.ec`, contraseña temporal igual a la cédula, cambio obligatorio antes del acceso. El alta ocurre en el servidor; no se guarda su clave en el repositorio. La matrícula no confirma la existencia del buzón. El estudiante entra con cédula y cambia su clave dentro de la página. No se ofrece recuperación por correo.

Cuenta docente: usuario visible `DocenteULEAM`, asociado al correo configurado en `teacherEmail`. La cuenta y perfil ya existen en Auth y la base de datos; la contraseña no se incluye en archivos. La aplicación obtiene el rol del servidor, no de un valor editable local.

RLS protege perfiles, matrículas y resultados. La evaluación valida inscripción, fechas y número de intentos, y calcula notas en una operación transaccional. No hay fallback a calificación local en una evaluación real. Los ajustes docentes conservan historial.

Se comprobaron inicios de sesión remotos de ambos roles, las tres materias de la docente, el perfil propio y bloqueo inicial por contraseña temporal del estudiante, el rechazo de altas desde el rol estudiante y el rechazo de lecturas anónimas. La recuperación por correo se retiró de la aplicación. El cambio de contraseña posterior quedó registrado en el servidor; la nueva contraseña es privada y no se utilizó en pruebas del entorno. La configuración para suprimir correos de Auth se documenta en `docs/SUPABASE.md`.

Los 48 bancos privados están cargados y verificados: 16 por materia, cinco retos por semana y 240 retos de evaluación con casos distintos de la práctica. Los 48 enunciados se consultaron mediante la sesión docente real y no incluyen campos de solución. Las 48 evaluaciones permanecen cerradas deliberadamente para que la docente revise los casos con **Ver evaluación**, en modo de solo lectura, y decida el calendario.

El corrector remoto se comprobó en una transacción SQL con contexto de identidad del estudiante y reversión completa: los 48 bancos calificaron respuestas correctas con 10 y erróneas con 0; reintentar el mismo identificador conservó cada resultado sin duplicarlo; los 48 bancos rechazaron un tercer intento nuevo. También se comprobaron cierre manual, plazo vencido y apertura futura. Después de revertir, quedaron cero notas guardadas, cero evaluaciones abiertas, 48 bancos y un único estudiante. La prueba no requirió conocer ni cambiar su nueva contraseña.

## Publicar y cambiar dirección

El workflow `.github/workflows/pages.yml` ejecuta pruebas y despliega `dist/` a GitHub Pages al subir a `main`. Seleccionar GitHub Actions en Settings → Pages. Rutas relativas permiten trasladar el mismo sitio a otro repositorio sin editar todos los enlaces.

El repositorio está en la organización académica `siginuleam` y la dirección gratuita con HTTPS es https://siginuleam.github.io/SIGIN-ULEAM/. `siteUrl`, las Redirect URLs de Auth y `SIGIN_ALLOWED_ORIGINS` usan esa dirección y su origen. No se necesita comprar un dominio ni configurar `CNAME`.

## Validación

Pruebas Node: 48 semanas/240 tareas, contexto suficiente, conservación de títulos, PDF, corrección de los formatos y ausencia de cálculos en las actividades incluidas, cuadrículas, importación y matrículas múltiples. Pruebas de adaptador/Edge: autenticación servidor, recuperación deshabilitada, refresh concurrente, altas autorizadas y rollback. PostgreSQL16 real: RLS, servidor de notas, límites simultáneos, horarios, cambio obligatorio y publicación privada.

Navegador: tres materias, cuatro formatos y cinco preguntas por semana, ambos temas visuales, acceso directo a prácticas y examen, plantilla Excel y layout en 360/390/768/1024/1440/1920 px. No equivale a validación de correo o permisos en el proyecto publicado.

Sitio publicado y Supabase real: inicio docente, tres materias, 48 semanas cerradas y revisión de un banco por materia. Cada vista mostró un caso y cinco preguntas, sin soluciones ni controles de entrega. La prueba fue de solo lectura y no cambió calendarios, notas ni contraseñas.

Las referencias enlazan documentos o apartados concretos y explican qué leer. Su comprobación HTTP externa quedó pendiente por la restricción de destinos del proxy del entorno; los destinos académicos se guardaron en el borrador de red para habilitarla. Esto no restringe los enlaces desde el navegador del alumnado.
