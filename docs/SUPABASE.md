# Activar cuentas y datos compartidos

La web exige inicio de sesión. El proyecto ya tiene las cuentas iniciales y la función de altas activas; el estado comprobado y lo pendiente aparecen a continuación. El plan Free de Supabase permite empezar sin pagar, con cuotas y posibles pausas por inactividad. Revisa los límites actuales en https://supabase.com/pricing.

## Estado de esta entrega

El proyecto remoto está activo. El esquema está aplicado y la URL y clave publicable están configuradas en el repositorio. La dirección académica https://siginuleam.github.io/SIGIN-ULEAM/ también está configurada en Auth como Site URL y Redirect URL. El registro público está desactivado y Auth admite claves temporales de diez caracteres.

- La cuenta docente y su perfil están creados. `DocenteULEAM` usa el correo configurado en `teacherEmail`; el inicio de sesión remoto devuelve las tres materias y el rol docente.
- Existe únicamente el estudiante de prueba autorizado, matriculado en las tres materias. Su sesión solo puede consultar su propio perfil. El usuario ya cambió su contraseña y el servidor registró que dejó de usar la clave temporal; su nueva contraseña permanece privada y no se usó en pruebas del entorno. Las altas futuras siguen exigiendo ese cambio antes de cargar el aula.
- `manage-students` está desplegada y activa, con la comprobación JWT heredada desactivada porque verifica cada sesión con Auth. Su secreto de orígenes admite `https://siginuleam.github.io`. Una petición docente sobre el estudiante existente respondió 200 y conservó la contraseña; una petición con rol estudiante fue rechazada con 403. La lectura anónima de perfiles devuelve 401.
- La recuperación por correo se retiró de la aplicación. El cambio de contraseña se realiza con una sesión activa dentro de la página. No se envían correos de prueba.
- Los 48 bancos privados están cargados y verificados: 16 por materia, cinco retos por semana, con un total de 240 retos de evaluación adicionales a los 240 de práctica. Usan casos nuevos y cinco preguntas de cuatro formatos: dos decisiones, relaciones, secuencia y crucigrama, sin cálculos. Los 48 enunciados se consultaron mediante una sesión docente real y no contienen campos de solución. Las 48 evaluaciones permanecen cerradas deliberadamente para que la docente las revise y configure el calendario.
- El corrector remoto pasó una comprobación SQL transaccional con contexto de identidad del estudiante: 10 para respuestas correctas y 0 para erróneas en los 48 bancos; 48 reintentos con el mismo identificador devolvieron el mismo intento sin duplicarlo; los 48 bancos rechazaron un tercer intento nuevo. También se comprobaron cierre manual, plazo vencido y apertura futura. Toda la transacción se revirtió: la comprobación posterior confirmó cero notas guardadas, cero evaluaciones abiertas, 48 bancos y un único estudiante. No se necesitó conocer ni cambiar su nueva contraseña.

Los pasos siguientes se conservan como instrucciones para mantener o reinstalar el proyecto; no hace falta repetir altas que ya existen. No se publican cédulas, contraseñas ni listados de personas.

El acceso administrativo del entorno cloud se configura mediante `SUPABASE_ACCESS_TOKEN` en **Secretos**. Se genera en https://supabase.com/dashboard/account/tokens y solo se utiliza contra `api.supabase.com` para administrar el proyecto elegido. No lo envíes al chat, no lo añadas a GitHub ni al frontend. La clave publicable no sustituye este acceso administrativo. El correo docente ya está asociado a `DocenteULEAM`; también puedes mantener la configuración desde el panel de Supabase.

## 1. Crear el proyecto

1. Abre https://supabase.com/dashboard y crea una cuenta, por ejemplo con GitHub.
2. Crea una organización y elige el plan **Free**.
3. Pulsa **New project**, usa un nombre académico, una región cercana y una contraseña de base de datos única. Guarda esa contraseña en un gestor; no la envíes al chat ni la subas a GitHub.
4. Cuando termine la creación, en **Project Settings → API / API Keys** copia **Project URL** y la clave **Publishable** (`sb_publishable_…`), o la clave heredada `anon` si el proyecto solo ofrece esa. Son datos públicos de conexión, protegidos por los permisos de la base de datos.
5. Configura estos dos datos en `assets/config.js`. La clave **Secret / service_role**, la contraseña de base de datos y los secretos SMTP nunca van allí.

## 2. Base de datos y docente

1. En **SQL Editor**, ejecuta `supabase/schema.sql`. Crea perfiles, tres materias, matrículas separadas, horarios e intentos. Las evaluaciones empiezan cerradas; las respuestas se guardan en un esquema privado.
2. En **Authentication → Providers / Sign In**, habilita Email y desactiva el registro público de nuevos usuarios. Solo la docente dará de alta estudiantes.
3. En **Authentication → Users**, crea el usuario docente con un correo bajo su control y la contraseña inicial acordada. Marca la cuenta como confirmada solo después de comprobar su titularidad. No escribas la contraseña en archivos SQL.
4. Copia su UUID de Authentication. En SQL Editor ejecuta este ejemplo **reemplazando el UUID**:

   ```sql
   insert into public.profiles(id, display_name, role, must_change_password)
   values ('UUID-DE-LA-DOCENTE', 'Docente', 'teacher', false);
   ```

5. Pon ese correo en `teacherEmail` dentro de `assets/config.js`. El usuario visible para entrar será `DocenteULEAM`; Auth valida el correo y la contraseña, y la base de datos valida el rol. El nombre visible no otorga permisos.
6. Ajusta en Authentication la longitud mínima a **10** para admitir la clave temporal solicitada. La web exige **12** para la clave definitiva. La cédula inicial es predecible: úsala solo para el alta controlada y solicita cambiarla de inmediato.

## 3. Autenticación sin correo

El usuario visible del estudiante y su contraseña temporal son su cédula. Supabase Auth conserva internamente `e{cedula}@live.uleam.edu.ec` para mantener las cuentas existentes; no se cambia ese identificador ni las contraseñas actuales. La función de altas usa Admin Create User con `email_confirm: true`, sin invitaciones. El cambio obligatorio pasa por `PUT /auth/v1/user`; el trigger existente libera el aula al cambiar el hash de Auth.

**Pendiente de aplicación remota:** el token administrativo del entorno devuelve HTTP 401 (`Invalid access token`). No se modificaron datos ni configuración remotos durante esta entrega.

Para suprimir también correos solicitados directamente a Auth, aplica `supabase/migrations/20261028_disable_auth_email.sql` y configura el hook Send Email mediante Management API: `hook_send_email_enabled: true`, `hook_send_email_uri: "pg-functions://postgres/public/sigin_suppress_auth_email"`. Desactiva todos los campos `mailer_notifications_*_enabled` y mantén `disable_signup: true`. El hook no entrega mensajes ni guarda su contenido. Verifica la configuración con una lectura administrativa y la función mediante SQL, sin invocar recuperación, OTP, invitaciones ni enviar correos de prueba. Estas operaciones no modifican usuarios, hashes, perfiles, matrículas ni notas.

Si se olvida una contraseña, se debe contactar a la docente para verificar la identidad y gestionar el acceso administrativamente.

## 4. Alta segura del único estudiante de prueba

La única cuenta de estudiante autorizada ya está creada y matriculada. Su cédula, nombre y clave no están en el repositorio público. Las altas futuras se realizan desde el panel docente. Para reinstalar la función de altas:

```sh
supabase login
supabase link --project-ref safynzirineolyxeitqh
supabase secrets set SIGIN_ALLOWED_ORIGINS=https://siginuleam.github.io
supabase functions deploy manage-students
```

`SIGIN_ALLOWED_ORIGINS` contiene orígenes, sin ruta: por ejemplo `https://organizacion.github.io`, aunque el sitio esté bajo `/SIGIN-ULEAM/`. Para desarrollo puedes añadir `http://localhost:4173` separado por coma. Supabase proporciona `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` a la función: no copies la clave al frontend. Si utilizas el editor web de Edge Functions, despliega el mismo código de `supabase/functions/manage-students/index.ts` y desactiva la verificación JWT heredada de la plataforma: la función valida cada sesión con Auth y comprueba el rol docente antes de usar permisos de servicio.

El panel permite alta manual o Excel con revisión. Cada persona tiene un perfil y puede matricularse en varias materias. El servidor genera su correo institucional y usa temporalmente su cédula como contraseña. La matrícula la autoriza la docente; eso no verifica que el buzón exista. La cuenta no puede consultar cursos ni enviar evaluaciones hasta cambiar la clave. El cambio se hace dentro de la página, con la sesión de contraseña temporal.

Al pulsar **Registrar**, el panel valida los campos y muestra **Guardando…**. Solo confirma el alta después de volver a leer el perfil y las matrículas desde Supabase. El correo se muestra antes del envío y se forma como `e{cédula}@live.uleam.edu.ec`; el sistema asocia ese identificador interno de Auth, no crea el buzón de Microsoft. Las matrículas existentes se reconocen sin volver a crear la cuenta. Excel conserva las filas pendientes y permite reintentar únicamente esas filas. Si se interrumpe una respuesta, consulta la lista antes de reintentar: la función comprueba el estado guardado y protege una cuenta cuyo resultado todavía no puede confirmar.

Si ya creaste manualmente una cuenta con el mismo correo pero sin perfil, completa su perfil/matrícula desde SQL Editor o elimínala si era una prueba vacía; el servicio no reasigna cuentas ajenas por coincidencia de correo.

## 5. Evaluaciones privadas

- La práctica tiene respuestas y retroalimentación pública para estudiar; ese contenido nunca es una prueba secreta.
- `private.assessment_keys` guarda **otro banco**, con `public_payload` sin respuestas y `answer_key` separado. `get_assessment` solo entrega el enunciado a alumnos matriculados dentro del horario. `submit_assessment` valida respuestas, fechas, intentos y califica en el servidor.
- No expongas `private` en **API → Exposed schemas**. No habilites acceso directo ni copies claves de evaluación al HTML o a JavaScript público.
- Un ejemplo de banco público de demostración no sirve para evaluar sin que se conozcan las respuestas. La docente debe revisar y cargar variantes privadas antes de abrir una evaluación real.
- Campos de claves: `id`, `type` (`choice`, `matching`, `order`, `numeric`, `crossword`), `correct`, `explanation` y opcionalmente `weight` / `tolerance`. Opción múltiple usa índice entero; emparejamiento y orden usan una permutación de índices; crucigrama usa una lista de palabras, normalizada en el servidor.
- El horario es un instante UTC; la interfaz presenta la hora de Ecuador. Una entrega fuera de horario se rechaza aunque la actividad ya estuviera abierta en la pantalla.
- Un ajuste docente agrega un registro con motivo sin borrar el historial ni consumir un intento del estudiante. Una entrega conserva un identificador único: reintentar la misma solicitud tras un corte de red devuelve el resultado guardado sin gastar otro intento.

### Cargar un banco desde el panel docente

Los bancos iniciales ya están cargados. Para revisar un banco sin modificarlo ni consumir intentos, abre **Espacio docente → Semanas y horarios**, selecciona materia y semana y pulsa **Ver evaluación**. La docente puede consultar el expediente y los enunciados aunque la evaluación esté cerrada.

Esta vista se comprobó en el sitio publicado con la cuenta docente y respuestas reales de Supabase: un banco de cada materia, con caso y cinco preguntas, sin campos de solución ni controles de entrega. La comprobación no cambió calendarios, notas, matrículas ni contraseñas.

Para sustituir o crear un banco, cierra primero la evaluación de esa semana. En **Espacio docente → Crear evaluación**, elige semana e introduce título, objetivo y expediente con datos suficientes. Añade los retos: opciones y posición correcta; relaciones; pasos en orden; o palabras y pistas del crucigrama. Incluye la explicación que se mostrará después de entregar. **Guardar evaluación privada** envía enunciados y claves separados al servidor, exige sesión docente y comprueba el formato. Después habilita la semana y configura sus fechas en **Semanas y horarios**.

La interfaz genera internamente `public_payload` (expediente y enunciados sin respuestas) y `answer_key` (claves y explicaciones). No subas esas claves al repositorio ni las distribuyas a estudiantes.

Ejemplo mínimo de **formato**, para adaptar con un caso y datos propios antes de evaluar:

```json
{
  "public_payload": {
    "context": "Expediente didáctico nuevo para la evaluación.",
    "questions": [
      {
        "id": "caso-nuevo-q1",
        "type": "choice",
        "prompt": "¿Qué permite seguir el estado del trámite, además de iniciar la solicitud?",
        "options": ["Publicar requisitos y un formulario descargable", "Asignar identificador y mostrar etapa actual y pasos pendientes", "Validar campos y confirmar la recepción del formulario"]
      }
    ]
  },
  "answer_key": [
    {
      "id": "caso-nuevo-q1",
      "type": "choice",
      "correct": 1,
      "explanation": "Un identificador unido al estado permite seguir el trámite. Descargar requisitos o confirmar recepción no informa las etapas posteriores."
    }
  ]
}
```

La plantilla ejemplifica el contrato; al estar documentada públicamente no es una evaluación secreta. El banco docente debe aportar preguntas diferentes. Cada pregunta pública necesita `id` y `type` iguales a su clave; las palabras del crucigrama pertenecen solo a `answer_key`, mientras sus pistas y posiciones van en el enunciado público.

`previewEnabled: false` ya está establecido: no hay botón de acceso público al aula. Las pruebas de navegador habilitan la vista previa solo mediante una configuración simulada. Las cuentas y permisos reales siempre se validan en el servidor.

## 6. Comprobación antes de producción

Prueba con dos cuentas temporales matriculadas en materias diferentes: cada una debe ver solo su matrícula y resultados. Un alumno no debe poder escribir su rol, editar notas, acceder a perfiles ajenos, abrir otra evaluación por URL ni leer `private.assessment_keys`. Comprueba cierre, límite de intentos, entrega concurrente, cambio de contraseña, ausencia de recuperación por correo y sincronización en dos dispositivos. Guarda una copia de seguridad y revisa privacidad y retención antes de cargar listados completos.

El proyecto, las cuentas iniciales, la función de altas, los 48 bancos privados y el corrector ya se comprobaron contra Supabase remoto. El servidor registró el cambio de contraseña previo del usuario. La nueva clave se conserva en privado. La docente debe revisar los bancos y programar sus fechas antes de abrir evaluaciones. Las comprobaciones transaccionales no guardaron notas ni dejaron semanas abiertas.

## Pruebas locales del adaptador y permisos

`npm test` incluye pruebas del adaptador y de la función con respuestas HTTP simuladas; no demuestra envío SMTP ni disponibilidad del proyecto remoto. El esquema se validó además en PostgreSQL 16 real con cuentas ficticias, RLS y entregas concurrentes. Para repetir esa comprobación en un contenedor **efímero**, sin conectar una base institucional:

```sh
docker run --rm -d --name sigin-sql-test -e POSTGRES_PASSWORD=sigin_test_fixture_only -e POSTGRES_DB=sigin_test postgres:16-alpine
docker exec sigin-sql-test pg_isready -U postgres -d sigin_test
# Cuando pg_isready confirme disponibilidad:
docker exec -i sigin-sql-test psql -v ON_ERROR_STOP=1 -U postgres -d sigin_test < supabase/tests/bootstrap.sql
docker exec -i sigin-sql-test psql -v ON_ERROR_STOP=1 -U postgres -d sigin_test < supabase/schema.sql
docker exec -i sigin-sql-test psql -v ON_ERROR_STOP=1 -U postgres -d sigin_test < supabase/tests/integration.sql
python3 supabase/tests/concurrency.py
docker stop sigin-sql-test
```

`bootstrap.sql` crea sustitutos mínimos de Auth para pruebas y **no debe ejecutarse en Supabase**. Los archivos de pruebas no contienen usuarios reales. El test concurrente necesita los fixtures de `integration.sql` y debe ejecutarse una vez por base efímera.
