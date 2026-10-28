import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(
  new URL("../../assets/backend.js", import.meta.url),
  "utf8",
);
const fixtureId = "0000000002";
const uuid = "00000000-0000-4000-8000-000000000002";
let serial = 0;
async function harness(responder) {
  const data = new Map();
  globalThis.sessionStorage = {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  };
  globalThis.location = {
    href: "https://aula.example.edu/SIGIN/",
    hash: "",
    pathname: "/SIGIN/",
    search: "",
  };
  globalThis.history = {
    replaceState: (_a, _b, url) => {
      globalThis.location.hash = "";
      globalThis.location.href = "https://aula.example.edu" + url;
    },
  };
  const requests = [];
  globalThis.fetch = async (url, options) => {
    const request = {
      url,
      ...options,
      body: options.body ? JSON.parse(options.body) : undefined,
    };
    requests.push(request);
    const result = await responder(request);
    return new Response(
      result.status === 204 ? null : JSON.stringify(result.body ?? null),
      {
        status: result.status || 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  };
  const config = {
    supabaseUrl: "https://test.supabase.co",
    supabasePublishableKey: "sb_publishable_fixture",
    teacherEmail: "teacher@example.edu",
    siteUrl: "https://aula.example.edu/SIGIN/",
  };
  const code =
    source.replace(
      /^import\s*\{\s*APP_CONFIG\s*\}\s*from\s*['"]\.\/config\.js['"];\s*/,
      `const APP_CONFIG=${JSON.stringify(config)};`,
    ) + `\n// fixture ${serial++}`;
  const module = await import(
    "data:text/javascript;base64," + Buffer.from(code).toString("base64")
  );
  return { ...module, requests, data };
}
function identity(request) {
  if (request.url.endsWith("/auth/v1/user")) return { body: { id: uuid } };
  if (request.url.includes("/profiles?"))
    return {
      body: [
        {
          id: uuid,
          student_number: fixtureId,
          display_name: "Prueba",
          role: "student",
          must_change_password: false,
        },
      ],
    };
  throw new Error("Unexpected request: " + request.url);
}
async function signedHarness(extra) {
  const h = await harness((request) => {
    if (request.url.includes("grant_type=password"))
      return {
        body: {
          access_token: "fixture-access",
          refresh_token: "fixture-refresh",
          expires_in: 3600,
        },
      };
    return extra?.(request) || identity(request);
  });
  await h.backend.login(fixtureId, fixtureId);
  return h;
}

test("login uses institutional email and authoritative server profile", async () => {
  const h = await signedHarness();
  assert.equal(h.requests[0].body.email, `e${fixtureId}@live.uleam.edu.ec`);
  assert.equal(h.requests[0].body.password, fixtureId);
  assert.equal((await h.backend.restore()).profile.role, "student");
  assert.equal(
    h.institutionalEmail(fixtureId),
    `e${fixtureId}@live.uleam.edu.ec`,
  );
  assert.throws(() => h.institutionalEmail("someone"), /diez dígitos/);
  assert.equal(h.requests[1].headers.Authorization, "Bearer fixture-access");
});

test("a forged local session cannot authorize an account or keep its role", async () => {
  const h = await harness(() => ({
    status: 401,
    body: { message: "JWT invalid" },
  }));
  h.data.set(
    "sigin-auth-session-v1",
    JSON.stringify({
      access_token: "fake",
      refresh_token: "fake",
      role: "teacher",
      expires_at: 9999999999,
    }),
  );
  await assert.rejects(h.backend.restore(), /sesión venció/);
  assert.equal(h.data.size, 0);
  assert.equal(h.requests.length, 1);
});

test("assessed questions and scoring go to server RPC, preserving typed answers", async () => {
  const h = await signedHarness((request) => {
    if (request.url.endsWith("/rpc/get_assessment"))
      return { body: { questions: [{ id: "a", type: "matching" }] } };
    if (request.url.endsWith("/rpc/submit_assessment"))
      return { body: { id: "attempt", score: 7.5, feedback: [] } };
  });
  assert.equal(
    (await h.backend.getAssessment("gig-502", 1)).questions.length,
    1,
  );
  assert.equal(
    (
      await h.backend.submitAssessment("gig-502", 1, [
        { id: "a", value: [1, 0] },
      ])
    ).score,
    7.5,
  );
  assert.deepEqual(h.requests.at(-1).body, {
    p_course_id: "gig-502",
    p_week: 1,
    p_answers: [{ id: "a", value: [1, 0] }],
  });
});

test("email recovery and invitation handlers are unavailable", async () => {
  const h = await harness(identity);
  assert.equal(h.backend.recover, undefined);
  assert.equal(h.backend.handleRecovery, undefined);
  assert.equal(h.requests.length, 0);
});

test("expired sessions refresh once for simultaneous requests", async () => {
  let refreshes = 0;
  const h = await signedHarness((request) => {
    if (request.url.includes("grant_type=refresh_token")) {
      refreshes++;
      return {
        body: {
          access_token: "new-access",
          refresh_token: "new-refresh",
          expires_in: 3600,
        },
      };
    }
    if (request.url.endsWith("/rpc/get_assessment"))
      return { body: { questions: [] } };
  });
  h.data.set(
    "sigin-auth-session-v1",
    JSON.stringify({
      access_token: "old",
      refresh_token: "fixture-refresh",
      expires_at: 1,
    }),
  );
  await Promise.all([
    h.backend.getAssessment("gig-502", 1),
    h.backend.getAssessment("gig-502", 2),
  ]);
  assert.equal(refreshes, 1);
  assert.equal(h.requests.at(-1).headers.Authorization, "Bearer new-access");
});

test("weekly schedule maps empty dates to SQL null and preserves actual instants", async () => {
  const h = await signedHarness((request) =>
    request.url.includes("/week_settings?")
      ? { body: [request.body] }
      : undefined,
  );
  await h.backend.saveWeek("gig-502", 1, {
    open: "",
    close: "",
    locked: false,
    maxAttempts: 2,
  });
  assert.equal(h.requests.at(-1).body.opens_at, null);
  assert.equal(h.requests.at(-1).body.closes_at, null);
  assert.equal(h.requests.at(-1).body.enabled, true);
  await h.backend.saveWeek("gig-502", 1, {
    open: "2026-10-10T08:00:00-05:00",
    close: "2026-10-11T08:00:00-05:00",
    locked: true,
    maxAttempts: 3,
  });
  assert.equal(h.requests.at(-1).body.opens_at, "2026-10-10T08:00:00-05:00");
  assert.equal(h.requests.at(-1).body.closes_at, "2026-10-11T08:00:00-05:00");
  assert.equal(h.requests.at(-1).body.max_attempts, 3);
});

test("multiple Excel rows for one person merge courses without losing each course parallel", async () => {
  const h = await signedHarness((request) =>
    request.url.endsWith("/functions/v1/manage-students")
      ? {
          body: {
            results: request.body.students.map((row) => ({
              id: row.id,
              ok: true,
            })),
          },
        }
      : undefined,
  );
  const result = await h.backend.provisionStudents([
    { id: fixtureId, name: "Prueba", courses: ["gig-502"], parallel: "A" },
    { id: fixtureId, name: "Prueba", courses: ["cex-103"], parallel: "C" },
  ]);
  assert.equal(result.imported, 1);
  const rows = h.requests.at(-1).body.students;
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].courses, ["gig-502", "cex-103"]);
  assert.deepEqual(rows[0].courseGroups, { "gig-502": "A", "cex-103": "C" });
  await assert.rejects(
    h.backend.provisionStudents([
      { id: fixtureId, name: "Prueba", courses: ["gig-502"] },
      { id: fixtureId, name: "Otro nombre", courses: ["cex-103"] },
    ]),
    /nombres diferentes/,
  );
});

test("submission forwards a stable nonce so a retry does not consume another attempt", async () => {
  const h = await signedHarness((request) =>
    request.url.endsWith("/rpc/submit_assessment")
      ? { body: { id: "saved-attempt", score: 10, feedback: [] } }
      : undefined,
  );
  const nonce = "10000000-0000-4000-8000-000000000001";
  await h.backend.submitAssessment(
    "gig-502",
    1,
    [{ id: "a", value: 1 }],
    nonce,
  );
  assert.equal(h.requests.at(-1).body.p_submission_id, nonce);
});

test("student registration validates rows before sending any account request", async () => {
  const h=await signedHarness();
  const before=h.requests.length;
  for (const row of [null,{id:fixtureId,name:"P",courses:["gig-502"]},{id:"bad",name:"Prueba",courses:["gig-502"]},{id:fixtureId,name:"Prueba",courses:[]}])
    await assert.rejects(h.backend.provisionStudents([row]),/filas|caracteres|dígitos|materia/);
  assert.equal(h.requests.length,before);
});

test("an incomplete registration response cannot be reported as success", async () => {
  const h=await signedHarness(request=>request.url.endsWith("/functions/v1/manage-students")?{body:{results:[]}}:undefined);
  const result=await h.backend.provisionStudents([{id:fixtureId,name:"Prueba",courses:["gig-502"]}]);
  assert.equal(result.imported,0);
  assert.equal(result.failed,1);
  assert.equal(result.results[0].code,"REGISTRATION_UNCONFIRMED");
  assert.match(result.results[0].error,/servidor no confirmó/);
});

test("an interrupted import preserves prior confirmations and does not send later batches", async () => {
  let calls=0;
  const h=await signedHarness(request=>{
    if(!request.url.endsWith("/functions/v1/manage-students")) return undefined;
    calls++;
    if(calls===2) throw new TypeError("Fetch failed");
    return {body:{results:request.body.students.map(row=>({id:row.id,ok:true}))}};
  });
  const rows=Array.from({length:51},(_,i)=>({id:String(i+20).padStart(10,"0"),name:"Estudiante de prueba",courses:["gig-502"]}));
  const result=await h.backend.provisionStudents(rows);
  assert.equal(calls,2);
  assert.equal(result.imported,25);
  assert.equal(result.failed,26);
  assert.equal(result.results[25].code,"REGISTRATION_UNCONFIRMED");
  assert.match(result.results[25].error,/conectar con el servidor/);
  assert.equal(result.results[50].code,"REGISTRATION_NOT_SENT");
});
