"""Exercise configured live UI against isolated Supabase route fixtures.

No real accounts, emails or grades are created. Install Python Playwright and run
SIGIN_TEST_URL=http://127.0.0.1:4173/SIGIN-ULEAM/ python scripts/browser_live_smoke.py.
"""
import copy
import json
import os
import re
import subprocess
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = os.environ.get('SIGIN_TEST_URL', 'http://127.0.0.1:4173/')
STUDENT_ID = '00000000-0000-4000-8000-000000000001'
STUDENT_NUMBER = '0000000000'
EMAIL = f'e{STUDENT_NUMBER}@live.uleam.edu.ec'
PASSWORD = 'PruebaSegura!2026'

# Reuse a real content fixture, while transmitting only public assessment fields.
fixture = json.loads(subprocess.check_output([
    'node', '--input-type=module', '-e',
    "import {courses} from './assets/courses.js'; "
    "import {crosswordLayout} from './assets/crossword.js'; "
    "const c=courses.find(c=>c.id==='gig-406');const a=c.activities[0];"
    "console.log(JSON.stringify({course:c,courses:courses.map(({id,code,name})=>({id,code,name})),activity:a,layouts:"
    "Object.fromEntries(a.questions.filter(q=>q.type==='crossword').map(q=>[q.id,crosswordLayout(q.entries)]))}));"
], cwd=ROOT))
course = fixture['course']
activity = fixture['activity']
public_payload = {k: copy.deepcopy(v) for k, v in activity.items() if k != 'questions'}
public_payload['name'] = 'Banco privado de prueba · cinco retos'
public_payload['questions'] = []
answers = []
answer_by_id = {}
for source in activity['questions']:
    q = {k: copy.deepcopy(v) for k, v in source.items()
         if k not in ('correct', 'explanation', 'tolerance')}
    if q['type'] == 'matching':
        q.pop('pairs')
        q['lefts'] = [p['left'] for p in source['pairs']]
        q['rights'] = [p['right'] for p in reversed(source['pairs'])]
        value = [len(source['pairs']) - i - 1 for i in range(len(source['pairs']))]
    elif q['type'] in ('ordering', 'order'):
        q['type'] = 'order'
        q['items'] = list(reversed(source['items']))
        value = list(reversed(range(len(q['items']))))
    elif q['type'] == 'crossword':
        value = [e['word'] for e in source['entries']]
        q['entries'] = [{'clue': e['clue'], 'length': len(e['word'])} for e in source['entries']]
        q['layout'] = copy.deepcopy(fixture['layouts'][source['id']])
        for cell in q['layout']['cells']:
            cell.pop('letter', None)
            cell.pop('directions', None)
        for placed in q['layout']['placed']:
            placed.pop('word', None)
    else:
        value = source['correct']
    public_payload['questions'].append(q)
    answers.append({'id': source['id'], 'value': value})
    answer_by_id[source['id']] = value
assert {q['type'] for q in public_payload['questions']} == {'choice', 'matching', 'order', 'crossword'}
assert len(public_payload['questions']) == 5
assert sum(q['type'] == 'choice' for q in public_payload['questions']) == 2
serialized = json.dumps(public_payload)
assert '"correct"' not in serialized and '"explanation"' not in serialized
assert '"pairs"' not in serialized and '"word"' not in serialized
for question in public_payload['questions']:
    if question['type'] == 'crossword':
        assert all('letter' not in cell for cell in question['layout']['cells'])

profile = {'id': STUDENT_ID, 'student_number': STUDENT_NUMBER,
           'display_name': 'Estudiante ficticio', 'role': 'student', 'must_change_password': False}
user = {'id': STUDENT_ID, 'email': EMAIL, 'user_metadata': {'role': 'teacher'}}
requests = []
attempts = []
errors = []
state = {'recovery_error': False, 'teacher_mode': False, 'bank_missing': False}
roster = [copy.deepcopy(profile)]
enrollments = [{'student_id': STUDENT_ID, 'course_id': course['id'], 'active': True, 'group_name': 'A'}]
# Only the isolated Edge fixture mutates these records. A subsequent roster fetch
# must use UUID-backed enrollments; optimistic rows or cédula-as-UUID would fail.
fixture_accounts = {}
state.update({'provision_error': None, 'provision_http_error': None, 'provision_invalid_response': False, 'provision_row_errors': {},
              'provision_hold': False, 'provision_pending': None, 'new_student': None})

def mock_supabase(route, record=True):
    request = route.request
    url = urlparse(request.url)
    path = url.path
    body = request.post_data_json if request.post_data else None
    if record:
        requests.append({'path': path, 'method': request.method, 'body': body, 'query': parse_qs(url.query)})
    if path == '/functions/v1/manage-students' and state['provision_hold']:
        state['provision_pending'] = route
        return
    response, status = None, 200
    if path == '/auth/v1/token':
        assert parse_qs(url.query)['grant_type'] == ['password']
        if state['new_student']:
            account = fixture_accounts[state['new_student']]
            assert body == {'email': account['email'], 'password': account['password']}
            auth_user = {'id': account['uuid'], 'email': account['email']}
        else:
            assert body['email'] == EMAIL
            auth_user = user
        response = {'access_token': 'fixture-access-token', 'refresh_token': 'fixture-refresh-token',
                    'expires_in': 3600, 'token_type': 'bearer', 'user': auth_user}
    elif path == '/auth/v1/user':
        if request.method == 'PUT':
            assert body == {'password': PASSWORD}
        response = {'id': fixture_accounts[state['new_student']]['uuid'], 'email': fixture_accounts[state['new_student']]['email']} if state['new_student'] else user
    elif path == '/auth/v1/logout':
        response = {}
    elif path == '/auth/v1/recover':
        assert body == {'email': EMAIL}
        redirect = parse_qs(url.query)['redirect_to'][0]
        assert urlparse(redirect).scheme == 'https' or urlparse(redirect).hostname in ('127.0.0.1', 'localhost')
        if state['recovery_error']:
            response, status = {'message': 'SMTP de prueba no disponible'}, 400
        else:
            response = {}
    elif path == '/rest/v1/profiles':
        if 'role=eq.student' in url.query:
            assert state['teacher_mode'], 'Student requested a teacher-only roster'
            response = roster
        else:
            if state['new_student']:
                response = [p for p in roster if p['student_number'] == state['new_student']]
            else:
                response = [{**profile, 'role': 'teacher', 'display_name': 'Docente ficticia'}] if state['teacher_mode'] else [profile]
    elif path == '/rest/v1/courses':
        response = fixture['courses'] if state['teacher_mode'] else [{'id': course['id'], 'code': course['code'], 'name': course['name']}]
    elif path == '/rest/v1/enrollments':
        response = enrollments
    elif path == '/rest/v1/week_settings':
        response = [{'course_id': course['id'], 'week': 1, 'enabled': not state['teacher_mode'], 'max_attempts': 2,
                     'opens_at': None, 'closes_at': None}]
    elif path == '/rest/v1/attempts':
        response = attempts
    elif path == '/rest/v1/practice_progress':
        response = []
    elif path == '/rest/v1/rpc/get_assessment':
        assert body == {'p_course_id': 'gig-406', 'p_week': 1}
        if state['bank_missing']:
            response, status = {'message': 'NO_ASSESSMENT_KEY'}, 400
        elif not state['teacher_mode'] and len(attempts) >= 2:
            response, status = {'message': 'ATTEMPTS_EXHAUSTED'}, 400
        else:
            response = public_payload
    elif path == '/rest/v1/rpc/submit_assessment':
        assert body['p_course_id'] == 'gig-406' and body['p_week'] == 1
        assert body['p_answers'] == answers, f"Unexpected submitted answers: {body['p_answers']}"
        response = {'score': 10, 'feedback': [
            {'id': q['id'], 'correct': True, 'explanation': q['explanation']}
            for q in activity['questions']]}
        attempts.append({'id': 'fixture-attempt-1', 'student_id': STUDENT_ID, 'course_id': 'gig-406',
                         'week': 1, 'score': 10, 'teacher_adjustment': False,
                         'created_at': '2026-10-08T12:00:00Z'})
    elif path == '/functions/v1/manage-students':
        assert state['teacher_mode'], 'Student invoked teacher provisioning'
        assert request.method == 'POST'
        assert request.headers['authorization'] == 'Bearer fixture-access-token'
        assert set(body) == {'students'}
        if state['provision_http_error']:
            response, status = {'error': state['provision_http_error']}, 503
        else:
            results = []
            for row in body['students']:
                number = row['id']
                assert re.fullmatch(r'\d{10}', number)
                assert 'email' not in row and 'password' not in row, 'Client must not override server-derived institutional credentials'
                institutional_email = f'e{number}@live.uleam.edu.ec'
                assert row['courses'] and all(c in {c['id'] for c in fixture['courses']} for c in row['courses']), row
                assert set(row['courseGroups']) == set(row['courses']), row
                assert all(isinstance(row['courseGroups'][c], str) and row['courseGroups'][c] for c in row['courses']), row
                row_error = state['provision_row_errors'].get(number) or state['provision_error']
                if row_error:
                    results.append({'id': number, 'ok': False, 'error': row_error})
                    continue
                existing = next((p for p in roster if p['student_number'] == number), None)
                created = existing is None
                if created:
                    uuid = f'00000000-0000-4000-8000-{int(number)+1:012d}'
                    existing = {'id': uuid, 'student_number': number, 'display_name': row['name'],
                                'role': 'student', 'must_change_password': True}
                    roster.append(existing)
                    fixture_accounts[number] = {'uuid': uuid, 'email': institutional_email, 'password': number}
                for selected_course in row['courses']:
                    assert existing['id'] != number
                    assert not any(e['student_id'] == existing['id'] and e['course_id'] == selected_course for e in enrollments)
                    enrollments.append({'student_id': existing['id'], 'course_id': selected_course,
                                        'active': True, 'group_name': row['courseGroups'][selected_course]})
                results.append({'id': number, 'ok': True, 'created': created})
            response = {'results': [] if state['provision_invalid_response'] else results}
    else:
        raise AssertionError(f'Unexpected request {request.method} {path}')
    route.fulfill(status=status, content_type='application/json', body=json.dumps(response),
                  headers={'Access-Control-Allow-Origin': '*'})

def normalize_word(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value) if c.isascii() and c.isalnum()).upper()

def assert_exam_without_teaching(scope):
    assert scope.locator('.reading-resources,.source-links,.reading-resource,.hint,.feedback,.answer-status').count() == 0
    assert scope.get_by_role('heading', name=re.compile(r'^Conceptos? claves?', re.I)).count() == 0
    assert scope.get_by_role('heading', name=re.compile(r'^Caso breve', re.I)).is_visible()
    expect(scope.locator('.exam-instructions')).to_be_visible()
    assert 'Responde las preguntas' in scope.locator('.exam-instructions').inner_text()
    for block in public_payload['context'].split('\n\n'):
        title, *paragraph = block.split('\n', 1)
        if re.match(r'^Conceptos?', title, re.I):
            assert scope.get_by_text(''.join(paragraph).strip(), exact=True).count() == 0
    for resource in public_payload.get('references', []):
        assert scope.locator('a[href="%s"]' % resource['url']).count() == 0
    for question in activity['questions']:
        assert scope.get_by_text(question['explanation'], exact=True).count() == 0

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    context.route('https://*.supabase.co/**', mock_supabase)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    page.goto(URL)
    page.locator('#login-form').wait_for()
    assert page.locator('[data-action="preview"]').count() == 0
    page.locator('#username').fill(STUDENT_NUMBER)
    page.locator('#password').fill('ClaveTemporalDePrueba')
    page.get_by_role('button', name='Entrar a mi aula', exact=False).click()
    page.locator('.course-card').wait_for()
    assert page.locator('.course-card').count() == 1
    assert course['name'] in page.locator('.course-card').inner_text()
    assert page.locator('[data-action="admin"]').count() == 0
    assert page.locator('[data-action="switchRole"]').count() == 0
    assert page.locator('[data-course="gig-502"], [data-course="gig-308"]').count() == 0
    assert 'Docente' not in page.locator('.profile').inner_text(), 'Untrusted user_metadata leaked into role'
    page.locator('.sidebar [data-action="settings"]').click()
    page.locator('[name="theme-choice"][value="dark"]').locator('..').click()
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    page.reload()
    page.locator('.course-card').wait_for()
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    assert page.evaluate("localStorage.getItem('sigin-theme-v1')") == 'dark'
    assert page.locator('.course-card').count() == 1

    page.evaluate("""() => { const b=document.createElement('button');b.dataset.action='switchRole';b.textContent='Intentar cambiar rol';document.querySelector('#app').append(b); }""")
    page.get_by_role('button', name='Intentar cambiar rol').click()
    assert page.locator('#toast').inner_text() == 'Cambiar de rol solo está disponible en la vista previa.'
    assert 'Docente' not in page.locator('.profile').inner_text()
    assert page.locator('[data-action="admin"]').count() == 0

    # Attempt navigation with injected controls; enrollment/profile guards must still apply.
    page.evaluate("""() => { const b=document.createElement('button');b.dataset.action='course';b.dataset.course='gig-502';b.textContent='Intentar otra materia';document.querySelector('#app').append(b); }""")
    page.get_by_role('button', name='Intentar otra materia').click()
    assert page.locator('#toast').inner_text() == 'Esta materia no está en tus matrículas.'
    assert page.locator('.course-card').count() == 1
    page.evaluate("""() => { const b=document.createElement('button');b.dataset.action='admin';b.textContent='Intentar panel docente';document.querySelector('#app').append(b); }""")
    page.get_by_role('button', name='Intentar panel docente').click()
    assert page.locator('#toast').inner_text() == 'Esta sección requiere una cuenta docente.'
    assert page.locator('#admin-course').count() == 0

    # Review is a teacher-only action, including controls inserted by a student.
    requests_before_review = len([r for r in requests if r['path'].endswith('/get_assessment')])
    page.evaluate("""() => { const b=document.createElement('button');b.dataset.action='reviewAssessment';b.dataset.week='1';b.textContent='Intentar revisión docente';document.querySelector('#app').append(b); }""")
    page.get_by_role('button', name='Intentar revisión docente').click()
    assert page.locator('#toast').inner_text() == 'Esta sección requiere una cuenta docente.'
    assert len([r for r in requests if r['path'].endswith('/get_assessment')]) == requests_before_review

    # The direct launcher preserves enrollments and closed weeks; practice still works.
    page.locator('.sidebar [data-action="activities"]').click()
    assert page.locator('#activity-course option').count() == 1
    assert page.locator('#activity-course').input_value() == course['id']
    page.locator('[data-action="activityMode"][data-mode="assessment"]').click()
    assert page.locator('[data-action="beginQuiz"][data-week="2"]').is_disabled()
    before_closed = len(requests)
    page.evaluate("""() => {const b=document.createElement('button');b.dataset.action='beginQuiz';b.dataset.course='gig-406';b.dataset.week='2';b.dataset.mode='assessment';b.textContent='Intentar examen cerrado';document.querySelector('#app').append(b);} """)
    page.get_by_role('button', name='Intentar examen cerrado').click()
    expect(page.locator('#toast')).to_have_text('Esta evaluación está cerrada.')
    assert page.locator('#quiz-answer').count() == 0
    assert len(requests) == before_closed
    page.evaluate("""() => {const b=document.createElement('button');b.dataset.action='beginQuiz';b.dataset.course='gig-502';b.dataset.week='1';b.dataset.mode='practice';b.textContent='Intentar práctica de otra materia';document.querySelector('#app').append(b);} """)
    page.get_by_role('button', name='Intentar práctica de otra materia').click()
    expect(page.locator('#toast')).to_have_text('Esta materia no está en tus matrículas.')
    assert page.locator('#quiz-answer').count() == 0
    page.locator('[data-action="activityMode"][data-mode="practice"]').click()
    second_week = page.locator('details.week').nth(1)
    second_week.locator('summary').click()
    second_week.locator('[data-action="beginQuiz"][data-mode="practice"]').click()
    assert page.locator('.case-reading-note').is_visible()
    assert page.locator('.quiz-dossier').get_attribute('open') is not None
    practice_question = page.evaluate("async()=>{const {courses}=await import('./assets/courses.js');return courses.find(c=>c.id==='gig-406').activities[1].questions[0];}")
    assert practice_question['type'] == 'choice'
    page.get_by_label(practice_question['options'][practice_question['correct']], exact=True).check()
    page.get_by_role('button', name='Comprobar mi respuesta', exact=False).click()
    assert page.get_by_role('heading', name='Bien razonado.').is_visible()
    assert page.get_by_text(practice_question['explanation'], exact=True).is_visible()
    page.get_by_role('button', name='Siguiente reto', exact=False).click()
    next_practice_question = page.evaluate("async()=>{const {courses}=await import('./assets/courses.js');return courses.find(c=>c.id==='gig-406').activities[1].questions[1];}")
    assert next_practice_question['type'] == 'choice'
    selected_option = page.get_by_label(next_practice_question['options'][next_practice_question['correct']], exact=True)
    selected_option.check()
    question_position = page.locator('.question-meta').inner_text()
    question_prompt = page.locator('.question-title').inner_text()
    assert 'Reto 2' in question_position
    for appearance in ['light', 'dark']:
        page.locator('.sidebar [data-action="settings"]').click()
        page.locator('#appearance-dialog').wait_for()
        page.locator('#appearance-dialog [name="theme-choice"][value="%s"]' % appearance).locator('..').click()
        expect(page.locator('html')).to_have_attribute('data-theme', appearance)
        page.locator('[data-action="closeSettings"]').click()
        assert page.locator('.question-meta').inner_text() == question_position
        assert page.locator('.question-title').inner_text() == question_prompt
        assert selected_option.is_checked()
        assert page.locator('#quiz-answer').count() == 1
    assert not [r for r in requests[before_closed:] if r['method'] != 'GET']
    page.get_by_role('button', name='Guardar y volver', exact=False).click()
    page.locator('[data-action="activityMode"][data-mode="assessment"]').click()
    page.locator('[data-action="beginQuiz"][data-week="1"][data-mode="assessment"]').click()
    page.get_by_role('heading', name=public_payload['name'], level=1).wait_for()
    assert page.locator('.case-reading-note').is_visible()
    assert page.locator('.quiz-dossier').get_attribute('open') is not None
    assert_exam_without_teaching(page)
    assert page.get_by_role('button', name='Comprobar mi respuesta', exact=False).count() == 0

    for index, q in enumerate(public_payload['questions']):
        value = answer_by_id[q['id']]
        if q['type'] == 'choice':
            page.get_by_label(q['options'][value], exact=True).check()
        elif q['type'] == 'matching':
            for left, right in enumerate(value):
                page.locator('[data-action="matchLeft"][data-index="%s"]' % left).click()
                page.locator('[data-action="matchRight"][data-index="%s"]' % right).click()
        elif q['type'] == 'order':
            for target, item_index in enumerate(value):
                current = page.locator('.order-text').all_text_contents().index(q['items'][item_index])
                while current > target:
                    page.locator('.order-item').nth(current).get_by_role('button').nth(0).click()
                    current -= 1
        elif q['type'] == 'crossword':
            for cell_index in range(page.locator('.cw-input').count()):
                cell = page.locator('.cw-input').nth(cell_index)
                ref = json.loads(cell.get_attribute('data-refs'))[0]
                cell.fill(normalize_word(value[ref['entry']])[ref['letter']])
        assert_exam_without_teaching(page)
        assert page.locator('#quiz-answer .correct,#quiz-answer .incorrect').count() == 0
        page.get_by_role('button', name='Revisar antes de terminar' if index == 4 else 'Siguiente reto', exact=False).click()
    page.get_by_role('heading', name='Revisa tu razonamiento.').wait_for()
    page.get_by_role('button', name='Confirmar y terminar').click()
    page.locator('.result-big').wait_for()
    assert page.locator('.result-big').inner_text().startswith('10.0')
    assert len([r for r in requests if r['path'].endswith('/submit_assessment')]) == 1
    for q in activity['questions']:
        assert page.get_by_text(q['explanation'], exact=True).is_visible()
    assert page.locator('[data-action="admin"]').count() == 0

    # Previously used attempts block the launcher and manually inserted controls.
    attempts.append({**attempts[0], 'id': 'fixture-attempt-2'})
    page.reload()
    page.locator('.course-card').wait_for()
    page.locator('.sidebar [data-action="activities"]').click()
    page.locator('[data-action="activityMode"][data-mode="assessment"]').click()
    assert page.locator('[data-action="beginQuiz"][data-week="1"]').is_disabled()
    requests_before_quota = len(requests)
    page.evaluate("""() => {const b=document.createElement('button');b.dataset.action='beginQuiz';b.dataset.course='gig-406';b.dataset.week='1';b.dataset.mode='assessment';b.textContent='Intentar examen sin intentos';document.querySelector('#app').append(b);} """)
    page.get_by_role('button', name='Intentar examen sin intentos').click()
    expect(page.locator('#toast')).to_have_text('Ya utilizaste tus intentos.')
    assert page.locator('#quiz-answer').count() == 0
    assert len(requests) == requests_before_quota

    # Password changes must use Auth; mismatch must not produce a request.
    page.locator('.side-nav').get_by_role('button', name='Mi cuenta', exact=True).click()
    page.get_by_role('button', name='Cambiar mi contraseña').click()
    page.locator('[name="password"]').fill(PASSWORD)
    page.locator('[name="confirm"]').fill('NoCoincide!2026')
    page.get_by_role('button', name='Guardar mi contraseña').click()
    assert page.locator('#password-status').inner_text() == 'Las contraseñas no coinciden.'
    assert not [r for r in requests if r['path'] == '/auth/v1/user' and r['method'] == 'PUT']
    page.locator('[name="confirm"]').fill(PASSWORD)
    page.get_by_role('button', name='Guardar mi contraseña').click()
    page.locator('.course-card').wait_for()
    assert len([r for r in requests if r['path'] == '/auth/v1/user' and r['method'] == 'PUT']) == 1
    page.locator('.side-nav').get_by_role('button', name='Salir', exact=True).click()
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')

    # No email recovery entry point or outbound recovery request.
    expect(page.get_by_role('button', name='Olvidé mi contraseña')).to_have_count(0)
    assert not [r for r in requests if r['path'] == '/auth/v1/recover']
    assert not [r for r in requests if r['path'].endswith('/publish_assessment') or r['path'].endswith('/manage-students')]

    # A validated teacher can inspect a closed bank without attempts or writes.
    state['teacher_mode'] = True
    page.locator('#username').fill(STUDENT_NUMBER)
    page.locator('#password').fill('ClaveTemporalDePrueba')
    page.get_by_role('button', name='Entrar a mi aula', exact=False).click()
    page.get_by_role('button', name='Espacio docente', exact=False).wait_for()
    page.get_by_role('button', name='Espacio docente', exact=False).click()
    page.locator('#admin-course').select_option(course['id'])
    week = page.locator('details.week').first
    week.locator('summary').click()
    assert week.locator('[name="locked"]').is_checked()
    state['bank_missing'] = True
    week.get_by_role('button', name='Ver evaluación', exact=False).click()
    expect(page.locator('#toast')).to_have_text('La docente todavía no ha publicado esta evaluación.')
    assert page.locator('.assessment-review').count() == 0
    state['bank_missing'] = False
    readonly_start = len(requests)
    attempt_count = len(attempts)
    week.get_by_role('button', name='Ver evaluación', exact=False).click()
    page.get_by_role('heading', name='Vista de evaluación', exact=True).wait_for()
    review = page.locator('.assessment-review')
    assert review.locator('.assessment-review-question').count() == 5
    assert review.locator('input,textarea,select,form,button').count() == 0
    for q in public_payload['questions']:
        assert review.get_by_role('heading', name=q['prompt'], exact=True).is_visible()
    assert_exam_without_teaching(review)
    for block in public_payload['context'].split('\n\n'):
        if block.startswith('Caso breve'):
            paragraph = block.split('\n', 1)[-1].strip()
            assert review.get_by_text(paragraph, exact=True).is_visible()
    assert review.get_by_text(public_payload['questions'][0]['options'][0], exact=True).is_visible()
    matching = next(q for q in public_payload['questions'] if q['type'] == 'matching')
    assert review.get_by_text(matching['lefts'][0], exact=True).is_visible()
    assert review.get_by_text(matching['rights'][0], exact=True).is_visible()
    crossword = next(q for q in public_payload['questions'] if q['type'] == 'crossword')
    assert review.get_by_text(crossword['entries'][0]['clue'], exact=False).is_visible()
    assert len(attempts) == attempt_count
    assert [r['path'] for r in requests[readonly_start:]] == ['/rest/v1/rpc/get_assessment']
    page.get_by_role('button', name='Volver a semanas y horarios', exact=False).click()
    page.locator('#admin-course').wait_for()
    assert page.locator('#admin-course').input_value() == course['id']
    assert page.locator('.assessment-review').count() == 0

    # Real frontend adapter and isolated Edge fixture: confirm persisted UUID-backed
    # profiles/matrículas, then exercise visible failure paths without optimistic success.
    page.get_by_role('button', name='Estudiantes', exact=True).click()
    def registrations():
        return [r for r in requests if r['path'].endswith('/manage-students')]
    def manual(number, name, parallel='B'):
        page.locator('#add-student [name="id"]').fill(number)
        if re.fullmatch(r'\d{10}', number):
            expect(page.locator('#student-email')).to_contain_text(f'e{number}@live.uleam.edu.ec')
        page.locator('#add-student [name="name"]').fill(name)
        page.locator('#add-student [name="parallel"]').fill(parallel)
        page.locator('#add-student [type="submit"]').click()
    def roster_count(count):
        expect(page.get_by_role('heading', name=f'Estudiantes de la materia ({count})', exact=True)).to_be_visible()
    def visible_failure(message):
        expect(page.locator('#manual-status,#import-status,#registration-summary').filter(has_text=message).first).to_be_visible()
        assert page.locator('.registration-status.success').count() == 0, 'A failed registration displayed success'
    def visible_success():
        success = page.locator('#manual-status,#registration-summary').filter(has_text=re.compile(r'confirmad[oa]s?.*Supabase', re.I)).first
        expect(success).to_be_visible()
        assert 'success' in success.get_attribute('class').split()
    roster_count(1)
    before_invalid = len(registrations())
    manual('12', '', '')
    expect(page.locator('#manual-status')).not_to_have_text('')
    manual('0000000009', '', 'A')
    expect(page.locator('#manual-status')).to_contain_text('nombres y apellidos')
    manual('0000000009', 'Estudiante sin paralelo', '')
    expect(page.locator('#manual-status')).to_contain_text('paralelo')
    assert len(registrations()) == before_invalid, 'Invalid manual form sent a provisioning request'
    start_registration = len(requests)
    state['provision_hold'] = True
    with page.expect_request('**/functions/v1/manage-students'):
        manual('0000000002', 'Estudiante alta individual', 'B')
    expect(page.locator('#manual-status')).to_contain_text(re.compile(r'guardando|registrando|comprobando', re.I))
    expect(page.locator('#add-student [type="submit"]')).to_be_disabled()
    deadline = time.monotonic() + 3
    while state['provision_pending'] is None and time.monotonic() < deadline:
        page.wait_for_timeout(10)
    assert state['provision_pending'] is not None, 'The fixture did not receive the pending registration'
    pending_count = len(registrations())
    page.locator('#add-student').evaluate('form=>form.requestSubmit()')
    assert len(registrations()) == pending_count, 'Submitting again while pending produced another registration'
    state['provision_hold'] = False
    mock_supabase(state['provision_pending'], record=False)
    state['provision_pending'] = None
    roster_count(2)
    visible_success()
    row = page.locator('#student-list tr').filter(has_text='0000000002')
    expect(row).to_contain_text('Estudiante alta individual')
    expect(row).to_contain_text('e0000000002@live.uleam.edu.ec')
    expect(row).to_contain_text(course['id'])
    assert fixture_accounts['0000000002']['uuid'] != '0000000002'
    assert enrollments[-1]['group_name'] == 'B'
    refresh_paths = [r['path'] for r in requests[start_registration:]]
    edge_index = refresh_paths.index('/functions/v1/manage-students')
    assert '/rest/v1/profiles' in refresh_paths[edge_index+1:] and '/rest/v1/enrollments' in refresh_paths[edge_index+1:]
    page.reload()
    page.get_by_role('button', name='Espacio docente', exact=False).click()
    page.locator('#admin-course').select_option(course['id'])
    page.get_by_role('button', name='Estudiantes', exact=True).click()
    roster_count(2)
    expect(page.locator('#student-list')).to_contain_text('e0000000002@live.uleam.edu.ec')

    before_duplicate = len(registrations())
    manual('0000000002', 'Nombre alternativo que no se debe guardar', 'Z')
    expect(page.locator('#manual-status,#registration-summary').filter(has_text=re.compile(r'ya.*inscrit|ya.*matricul', re.I)).first).to_be_visible()
    assert len(registrations()) == before_duplicate
    roster_count(2)
    expect(page.locator('#student-list')).to_contain_text('Estudiante alta individual')
    assert next(e for e in enrollments if e['student_id'] == fixture_accounts['0000000002']['uuid'] and e['course_id'] == course['id'])['group_name'] == 'B'

    # HTTP and per-row failures keep the submitted fields and explain the result.
    state['provision_http_error'] = 'Servidor de alta no disponible (fixture).'
    manual('0000000003', 'Estudiante fallo temporal')
    visible_failure(state['provision_http_error'])
    assert page.locator('#add-student [name="id"]').input_value() == '0000000003'
    roster_count(2)
    assert '0000000003' not in fixture_accounts
    state['provision_http_error'] = None
    state['provision_error'] = 'La matrícula ficticia no se pudo guardar.'
    manual('0000000003', 'Estudiante fallo temporal')
    visible_failure(state['provision_error'])
    assert page.locator('#add-student [name="id"]').input_value() == '0000000003'
    roster_count(2)
    assert '0000000003' not in fixture_accounts
    state['provision_error'] = None
    manual('0000000003', 'Estudiante fallo temporal')
    roster_count(3)
    expect(page.locator('#student-list')).to_contain_text('e0000000003@live.uleam.edu.ec')

    # Load a real workbook through the bundled Excel library and the UI preview.
    with page.expect_download() as downloaded:
        page.get_by_role('button', name='Descargar plantilla Excel').click()
    assert downloaded.value.suggested_filename.endswith('.xlsx')
    def excel_rows(student_rows):
        previous_names = page.locator('#import-preview tbody tr td:nth-child(2)').all_text_contents()
        buffer = page.evaluate("""async rows => {const wb=new ExcelJS.Workbook();const sheet=wb.addWorksheet('SIGIN');sheet.addRows(rows);return Array.from(new Uint8Array(await wb.xlsx.writeBuffer()));}""",
                               [['Cédula', 'Nombres y Apellidos', 'Materia', 'Paralelo'], *student_rows])
        path = Path(f'/tmp/sigin-student-fixture-{student_rows[0][0]}.xlsx')
        path.write_bytes(bytes(buffer))
        page.locator('#import-file').set_input_files(path)
        for previous in set(previous_names) - {row[1] for row in student_rows}:
            expect(page.locator('#import-preview')).not_to_contain_text(previous)
        for row in student_rows:
            expect(page.locator('#import-preview')).to_contain_text(row[1])
        expect(page.locator('#import-preview tbody tr')).to_have_count(len(student_rows))
        return page.locator('[data-action="confirmImport"]')
    def excel_file(number, name, code):
        return excel_rows([[number, name, code, 'C']])
    before_excel = len(registrations())
    confirmation = excel_file('0000000004', 'Estudiante Excel ficticio', course['code'])
    expect(confirmation).to_be_enabled()
    expect(page.locator('#import-status')).to_contain_text('Aún no se ha guardado ninguna')
    assert len(registrations()) == before_excel
    state['provision_http_error'] = 'Error ficticio al guardar Excel.'
    confirmation.click()
    visible_failure(state['provision_http_error'])
    roster_count(3)
    assert '0000000004' not in fixture_accounts
    state['provision_http_error'] = None
    confirmation.click()
    roster_count(4)
    visible_success()
    expect(page.locator('#student-list')).to_contain_text('e0000000004@live.uleam.edu.ec')
    assert registrations()[-1]['body']['students'][0]['courses'] == [course['id']], 'Excel course code was not normalized to a database id'

    state['provision_error'] = 'Fila Excel ficticia pendiente.'
    excel_file('0000000005', 'Estudiante Excel rechazado', course['id']).click()
    visible_failure(state['provision_error'])
    roster_count(4)
    assert '0000000005' not in fixture_accounts
    state['provision_error'] = None

    # Mixed Excel results must keep the committed row, expose the rejected row,
    # and retry only what remains pending instead of provisioning it twice.
    state['provision_row_errors'] = {'0000000007': 'Una fila Excel ficticia quedó pendiente.'}
    excel_rows([['0000000006', 'Estudiante Excel confirmado', course['code'], 'C'],
                ['0000000007', 'Estudiante Excel pendiente', course['code'], 'C']]).click()
    expect(page.locator('#import-status,#registration-summary').filter(has_text=state['provision_row_errors']['0000000007']).first).to_be_visible()
    roster_count(5)
    assert '0000000006' in fixture_accounts and '0000000007' not in fixture_accounts
    expect(page.locator('#student-list')).to_contain_text('e0000000006@live.uleam.edu.ec')
    state['provision_row_errors'] = {}
    page.locator('[data-action="confirmImport"]').click()
    roster_count(6)
    assert [row['id'] for row in registrations()[-1]['body']['students']] == ['0000000007']
    visible_success()

    # Simulate a committed account whose Edge confirmation is incomplete. The
    # frontend must report uncertainty, preserve the form and recover from an
    # authoritative roster read without creating the same account a second time.
    state['provision_invalid_response'] = True
    manual('0000000008', 'Estudiante respuesta incierta', 'E')
    visible_failure('El servidor no confirmó todos los registros.')
    assert page.locator('#add-student [name="id"]').input_value() == '0000000008'
    assert '0000000008' in fixture_accounts
    saved_uuid = fixture_accounts['0000000008']['uuid']
    assert any(e['student_id'] == saved_uuid and e['course_id'] == course['id'] for e in enrollments)
    state['provision_invalid_response'] = False
    page.reload()
    page.get_by_role('button', name='Espacio docente', exact=False).click()
    page.locator('#admin-course').select_option(course['id'])
    page.get_by_role('button', name='Estudiantes', exact=True).click()
    roster_count(7)
    before_recovery = len(registrations())
    manual('0000000008', 'Estudiante respuesta incierta', 'E')
    visible_success()
    assert len(registrations()) == before_recovery
    assert fixture_accounts['0000000008']['uuid'] == saved_uuid

    # One person can belong to two courses, retaining one account/profile UUID.
    second_course = next(c for c in fixture['courses'] if c['id'] != course['id'])
    page.locator('#admin-course').select_option(second_course['id'])
    manual('0000000002', 'Estudiante alta individual', 'D')
    roster_count(1)
    expect(page.locator('#student-list')).to_contain_text('e0000000002@live.uleam.edu.ec')
    assert registrations()[-1]['body']['students'][0]['courses'] == [second_course['id']]
    assert len([p for p in roster if p['student_number'] == '0000000002']) == 1
    assert len([e for e in enrollments if e['student_id'] == fixture_accounts['0000000002']['uuid']]) == 2
    page.locator('.sidebar [data-action="logout"]').click()
    state['teacher_mode'], state['new_student'] = False, '0000000004'
    page.locator('#username').fill('0000000004')
    page.locator('#password').fill('0000000004')
    page.get_by_role('button', name='Entrar a mi aula', exact=False).click()
    page.get_by_role('heading', name='Elige tu nueva contraseña.', exact=True).wait_for()
    assert page.locator('.app-shell,.course-card').count() == 0
    assert 'Antes de entrar, cambia la clave temporal' in page.locator('main').inner_text()
    assert not errors, errors
    assert not [r for r in requests if r['path'].endswith('/publish_assessment')]
    print('PASS: isolated live Auth; practice/exam enrollment, calendar and quota guards; exam/review case without teaching or resources; server grading and disabled email recovery; manual pending/email/UUID persistence; invalid/duplicate/HTTP/row failures visible; cleared stale Excel preview, partial import and failed-only retry; uncertain committed response reconciled without duplicate POST; new account must change cédula password; no JS errors')
    browser.close()
