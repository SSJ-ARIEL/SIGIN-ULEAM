import { APP_CONFIG } from "./config.js";

const SESSION_KEY = "sigin-auth-session-v1";
export const backendConfigured = Boolean(
  APP_CONFIG.supabaseUrl && APP_CONFIG.supabasePublishableKey,
);
export function institutionalEmail(username) {
  const id = String(username ?? "").trim();
  if (!/^\d{10}$/.test(id))
    throw new Error("Ingresa una cédula de diez dígitos.");
  return `e${id}@live.uleam.edu.ec`;
}
function emailFor(username) {
  if (String(username).trim().toLowerCase() === "docenteuleam") {
    if (!APP_CONFIG.teacherEmail)
      throw new Error("Falta configurar el correo de la docente.");
    return APP_CONFIG.teacherEmail.trim();
  }
  return institutionalEmail(username);
}
function currentSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}
function remember(session) {
  if (!session?.access_token || !session?.refresh_token) return;
  sessionStorage.setItem(
    SESSION_KEY,
    JSON.stringify({
      access_token: session.access_token,
      refresh_token: session.refresh_token,
      expires_at:
        session.expires_at ||
        Math.floor(Date.now() / 1000) + Number(session.expires_in || 3600),
    }),
  );
}
function errorText(data, status) {
  const message = String(
    data?.msg || data?.message || data?.error_description || data?.error || "",
  );
  const known = {
    "Invalid login credentials": "Usuario o contraseña incorrectos.",
    "Email not confirmed": "Contacta a la docente para habilitar tu cuenta.",
    WINDOW_CLOSED: "La evaluación está cerrada o fuera de su horario.",
    SUBMISSION_ID_REUSED:
      "Esta entrega ya existe con otras respuestas. Recarga la actividad antes de volver a enviar.",
    ATTEMPTS_EXHAUSTED: "Ya utilizaste los intentos disponibles.",
    NOT_ENROLLED: "No tienes una matrícula activa en esta materia.",
    PASSWORD_CHANGE_REQUIRED:
      "Debes cambiar tu contraseña temporal antes de entrar al aula.",
    CLOSE_BEFORE_PUBLISH:
      "Cierra la evaluación antes de sustituir sus preguntas.",
    ANSWER_IN_PUBLIC_PAYLOAD:
      "El enunciado público contiene respuestas. Sepáralas en answer_key.",
    INVALID_ASSESSMENT_BANK:
      "El banco de preguntas no tiene un formato válido.",
    NO_ASSESSMENT_KEY: "La docente todavía no ha publicado esta evaluación.",
    INVALID_ANSWERS:
      "La entrega contiene respuestas incompletas o con formato incorrecto.",
    TEACHER_REQUIRED: "Esta acción requiere una cuenta docente.",
  };
  for (const [key, value] of Object.entries(known))
    if (message.includes(key)) return value;
  if (status === 429)
    return "Demasiados intentos. Espera unos minutos antes de volver a intentar.";
  if (status === 401) return "La sesión venció. Vuelve a ingresar.";
  return message || `No se pudo completar la operación (${status}).`;
}
async function raw(path, { method = "GET", body, token, headers = {} } = {}) {
  if (!backendConfigured)
    throw new Error("La conexión institucional todavía no está configurada.");
  let response;
  try {
    response = await fetch(
      `${APP_CONFIG.supabaseUrl.replace(/\/$/, "")}${path}`,
      {
        method,
        headers: {
          apikey: APP_CONFIG.supabasePublishableKey,
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...headers,
        },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      },
    );
  } catch {
    throw new Error(
      "No se pudo conectar con el servidor. Revisa tu conexión y vuelve a intentar.",
    );
  }
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) throw new Error(errorText(data, response.status));
  return data;
}
let refreshPromise;
async function token() {
  const session = currentSession();
  if (!session) throw new Error("Inicia sesión para continuar.");
  if (session.expires_at > Math.floor(Date.now() / 1000) + 60)
    return session.access_token;
  if (!refreshPromise)
    refreshPromise = raw("/auth/v1/token?grant_type=refresh_token", {
      method: "POST",
      body: { refresh_token: session.refresh_token },
    })
      .then((next) => {
        remember(next);
        return next.access_token;
      })
      .catch((error) => {
        sessionStorage.removeItem(SESSION_KEY);
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  return refreshPromise;
}
async function api(path, options = {}) {
  return raw(path, { ...options, token: await token() });
}
async function validatedIdentity() {
  const user = await api("/auth/v1/user"); // El servidor valida el token; nunca confiar en role de localStorage.
  const profiles = await api(
    `/rest/v1/profiles?id=eq.${encodeURIComponent(user.id)}&select=id,student_number,display_name,role,must_change_password`,
  );
  const profile = profiles?.[0];
  if (!profile || !["student", "teacher"].includes(profile.role))
    throw new Error(
      "Tu cuenta no tiene un perfil autorizado. Contacta a la docente.",
    );
  return { user, profile };
}

export const backend = Object.freeze({
  async login(username, password) {
    const session = await raw("/auth/v1/token?grant_type=password", {
      method: "POST",
      body: { email: emailFor(username), password },
    });
    remember(session);
    try {
      return await validatedIdentity();
    } catch (error) {
      sessionStorage.removeItem(SESSION_KEY);
      throw error;
    }
  },
  async restore() {
    if (!backendConfigured || !currentSession()) return null;
    try {
      return await validatedIdentity();
    } catch (error) {
      sessionStorage.removeItem(SESSION_KEY);
      throw error;
    }
  },
  async logout() {
    try {
      if (currentSession()) await api("/auth/v1/logout", { method: "POST" });
    } finally {
      sessionStorage.removeItem(SESSION_KEY);
    }
  },
  async updatePassword(password) {
    const identity = await validatedIdentity();
    if (String(password).length < 12)
      throw new Error("Usa una contraseña de al menos doce caracteres.");
    if (password === identity.profile.student_number)
      throw new Error("La nueva contraseña debe ser distinta de tu cédula.");
    await api("/auth/v1/user", { method: "PUT", body: { password } });
    return validatedIdentity(); // Un trigger del servidor libera el aula después del cambio.
  },
  async loadWorkspace() {
    const { profile } = await validatedIdentity();
    if (profile.must_change_password)
      return {
        profile,
        courses: [],
        enrollments: [],
        settings: [],
        attempts: [],
        practice: [],
      };
    const [courses, enrollments, settings, attempts, practice, students] =
      await Promise.all([
        api("/rest/v1/courses?select=*&order=name"),
        api("/rest/v1/enrollments?select=*"),
        api("/rest/v1/week_settings?select=*&order=week"),
        api("/rest/v1/attempts?select=*&order=created_at"),
        api("/rest/v1/practice_progress?select=*"),
        profile.role === "teacher"
          ? api(
              "/rest/v1/profiles?role=eq.student&select=id,student_number,display_name,role,must_change_password",
            )
          : Promise.resolve([]),
      ]);
    return {
      profile,
      courses,
      enrollments,
      settings,
      attempts,
      practice,
      students,
    };
  },
  async saveWeek(courseId, week, settings) {
    const cleanDate = (value) =>
      typeof value === "string" ? value.trim() || null : (value ?? null);
    const record = {
      course_id: courseId,
      week: Number(week),
      opens_at: cleanDate(settings.opens_at ?? settings.open),
      closes_at: cleanDate(settings.closes_at ?? settings.close),
      enabled: settings.enabled ?? !settings.locked,
      max_attempts: Number(settings.max_attempts ?? settings.maxAttempts ?? 2),
    };
    return api("/rest/v1/week_settings?on_conflict=course_id,week", {
      method: "POST",
      body: record,
      headers: { Prefer: "resolution=merge-duplicates,return=representation" },
    });
  },
  async publishAssessment(courseId, week, publicPayload, answerKey) {
    return api("/rest/v1/rpc/publish_assessment", {
      method: "POST",
      body: {
        p_course_id: courseId,
        p_week: Number(week),
        p_public_payload: publicPayload,
        p_answer_key: answerKey,
      },
    });
  },
  async getAssessment(courseId, week) {
    return api("/rest/v1/rpc/get_assessment", {
      method: "POST",
      body: { p_course_id: courseId, p_week: Number(week) },
    });
  },
  async submitAssessment(courseId, week, answers, submissionId) {
    return api("/rest/v1/rpc/submit_assessment", {
      method: "POST",
      body: {
        p_course_id: courseId,
        p_week: Number(week),
        p_answers: answers,
        ...(submissionId ? { p_submission_id: submissionId } : {}),
      },
    });
  },
  async savePractice(courseId, week) {
    return api(
      "/rest/v1/practice_progress?on_conflict=student_id,course_id,week",
      {
        method: "POST",
        body: {
          student_id: (await validatedIdentity()).profile.id,
          course_id: courseId,
          week: Number(week),
          completed_at: new Date().toISOString(),
        },
        headers: {
          Prefer: "resolution=merge-duplicates,return=representation",
        },
      },
    );
  },
  async provisionStudents(rows) {
    if (!Array.isArray(rows) || !rows.length)
      throw new Error("Selecciona al menos un estudiante válido.");
    const grouped = new Map();
    for (const row of rows) {
      if (!row || typeof row !== "object" || Array.isArray(row))
        throw new Error(
          "Revisa las filas: cada estudiante necesita cédula, nombre y materia.",
        );
      const id = String(row.id || row.cedula || "").trim();
      const name = String(row.name || row.nombre || "").trim();
      const courses = Array.isArray(row.courses)
        ? [
            ...new Set(
              row.courses.map((value) =>
                typeof value === "string" ? value.trim() : "",
              ),
            ),
          ]
        : row.courseId
          ? [typeof row.courseId === "string" ? row.courseId.trim() : ""]
          : [];
      if (!/^\d{10}$/.test(id))
        throw new Error("Cédula: se requieren diez dígitos.");
      if (name.length < 2 || name.length > 120)
        throw new Error("Ingresa nombres y apellidos de entre 2 y 120 caracteres.");
      if (!courses.length || courses.some((value) => !value))
        throw new Error("Selecciona la materia para registrar al estudiante.");
      const existing = grouped.get(id);
      if (existing && existing.name !== name)
        throw new Error(
          "La misma cédula tiene nombres diferentes. Revisa las filas antes de registrar.",
        );
      const entry = existing || {
        id,
        name,
        courses: [],
        courseGroups: {},
      };
      for (const course of courses) {
        const group = String(
          row.courseGroups?.[course] ?? row.group ?? row.parallel ?? "",
        ).trim();
        if (
          entry.courses.includes(course) &&
          entry.courseGroups[course] !== group
        )
          throw new Error(
            "La misma matrícula tiene paralelos diferentes. Revisa las filas.",
          );
        if (!entry.courses.includes(course)) entry.courses.push(course);
        entry.courseGroups[course] = group;
      }
      grouped.set(id, entry);
    }
    const students = [...grouped.values()];
    const results = [];
    // Cada lote tiene resultados explícitos; las filas fallidas pueden reintentarse sin duplicar matrículas.
    for (let start = 0; start < students.length; start += 25) {
      const batch = students.slice(start, start + 25);
      try {
        const part = await api("/functions/v1/manage-students", {
          method: "POST",
          body: { students: batch },
        });
        const expected = new Set(batch.map((row) => row.id));
        if (
          !Array.isArray(part?.results) ||
          part.results.length !== batch.length ||
          part.results.some(
            (row) =>
              !row ||
              typeof row.ok !== "boolean" ||
              (!row.ok && typeof row.error !== "string") ||
              !expected.delete(row.id),
          ) ||
          expected.size
        )
          throw new Error(
            "El servidor no confirmó todos los registros. Revisa la lista antes de reintentar.",
          );
        results.push(...part.results);
      } catch (error) {
        // Una respuesta perdida no demuestra que el servidor no haya guardado el lote.
        // Conservar los resultados anteriores y no enviar los lotes restantes.
        const message =
          error instanceof Error
            ? error.message
            : "No se pudo confirmar el registro.";
        for (const row of students.slice(start))
          results.push({
            id: row.id,
            ok: false,
            code: batch.includes(row)
              ? "REGISTRATION_UNCONFIRMED"
              : "REGISTRATION_NOT_SENT",
            error: batch.includes(row)
              ? `${message} No se recibió confirmación de este registro; revisa si aparece en la lista antes de reintentar.`
              : "Este registro no se envió porque se interrumpió el lote anterior.",
          });
        break;
      }
    }
    return {
      results,
      imported: results.filter((row) => row.ok).length,
      failed: results.filter((row) => !row.ok).length,
    };
  },
  async adjustGrade(studentUuid, courseId, week, score, reason) {
    return api("/rest/v1/rpc/adjust_grade", {
      method: "POST",
      body: {
        p_student_id: studentUuid,
        p_course_id: courseId,
        p_week: Number(week),
        p_score: Number(score),
        p_reason: reason,
      },
    });
  },
  async updateEnrollment(studentUuid, courseId, active) {
    return api(
      `/rest/v1/enrollments?student_id=eq.${encodeURIComponent(studentUuid)}&course_id=eq.${encodeURIComponent(courseId)}`,
      {
        method: "PATCH",
        body: { active: Boolean(active) },
        headers: { Prefer: "return=representation" },
      },
    );
  },
});
