"""Test closed public access, then opt into preview through a local test fixture."""
import json, os, re, subprocess, unicodedata
from pathlib import Path
from playwright.sync_api import expect, sync_playwright
root=Path(__file__).resolve().parents[1]
data=json.loads(subprocess.check_output(['node','--input-type=module','-e',"import {courses} from './assets/courses.js'; console.log(JSON.stringify(courses))"],cwd=root))
assert {q['type'] for c in data for a in c['activities'] for q in a['questions']}=={'choice','matching','ordering','crossword'}
def word(s):return ''.join(c for c in unicodedata.normalize('NFD',s) if c.isascii() and c.isalnum()).upper()
def choose_theme(page, preference, guest=False):
 page.set_viewport_size({'width':1440,'height':1000})
 page.locator('[data-action="settings"]').click()
 radio=page.locator('[name="theme-choice"][value="%s"]'%preference)
 radio.locator('..').click()
 assert radio.is_checked()
 if guest:page.locator('[data-action="closeSettings"]').click()
 stored=page.evaluate("localStorage.getItem('sigin-theme-v1')")
 assert stored==preference or (preference=='system' and stored is None),stored
 if preference!='system':expect(page.locator('html')).to_have_attribute('data-theme',preference)
def input_readable(locator):
 assert locator.is_visible()
 box=locator.bounding_box()
 assert box['width']>=200 and box['height']>=40,box
 text_readable(locator)
def text_readable(locator):
 contrast=locator.evaluate("""el=>{
  const rgb=s=>s.match(/[\\d.]+/g).map(Number);
  let node=el,bg;
  while(node){bg=rgb(getComputedStyle(node).backgroundColor);if(bg.length===3||bg[3]===1)break;node=node.parentElement;}
  const luminance=v=>v.slice(0,3).map(c=>c/255).map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4).reduce((sum,c,i)=>sum+c*[.2126,.7152,.0722][i],0);
  const ratio=(color,opacity=1)=>{const fg=rgb(color),alpha=(fg.length===4?fg[3]:1)*opacity;const blended=fg.slice(0,3).map((c,i)=>c*alpha+bg[i]*(1-alpha));const a=luminance(blended),b=luminance(bg);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05);};
  const result={text:ratio(getComputedStyle(el).color)};
  if(el.getAttribute('placeholder')){const style=getComputedStyle(el,'::placeholder');result.placeholder=ratio(style.color,Number(style.opacity));}
  return result;
 } """)
 assert all(value>=4.5 for value in contrast.values()),contrast
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 public_page=browser.new_page()
 public_errors=[]
 public_page.on('pageerror', lambda e: public_errors.append(str(e)))
 public_page.goto(os.environ.get('SIGIN_TEST_URL','http://127.0.0.1:4173/'))
 public_page.locator('#login-form').wait_for()
 assert public_page.get_by_role('button',name='Explorar las tres materias').count()==0
 expect(public_page.locator('.landing-copy h1')).to_be_visible()
 expect(public_page.locator('.landing-composition')).to_have_attribute('aria-hidden','true')
 assert public_page.locator('.landing-story img').count()==0
 surfaces={}
 for appearance in ['light','dark']:
  choose_theme(public_page,appearance,guest=True)
  surfaces[appearance]=public_page.locator('.login-panel').evaluate('el=>getComputedStyle(el).backgroundColor')
  public_page.reload()
  public_page.locator('#login-form').wait_for()
  expect(public_page.locator('html')).to_have_attribute('data-theme',appearance)
  expect(public_page.locator('meta[name="theme-color"]')).to_have_attribute('content','#1c1817' if appearance=='dark' else '#f8f4ed')
  for selector in ['#login-form .primary','.role-switch button.active','.login-help','.landing h1 em']:
   text_readable(public_page.locator(selector))
  for width in [1920,1440,1024,768,390,360]:
   public_page.set_viewport_size({'width':width,'height':1000})
   assert public_page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(appearance,width)
   for selector in ['#username','#password']:input_readable(public_page.locator(selector))
   if width in [1440,360]:public_page.screenshot(path=f'/tmp/sigin-login-{appearance}-{width}.png',full_page=True)
  # Text leads the minimal hero; the login CTA stays in the first screen on
  # ordinary laptop/phone sizes. Desktop hero and form remain separate columns.
  for width,height in [(1366,768),(360,844)]:
   public_page.set_viewport_size({'width':width,'height':height})
   public_page.evaluate("window.scrollTo({top:0,left:0,behavior:'instant'})")
   story=public_page.locator('.landing-story').bounding_box()
   headline=public_page.locator('.landing h1').bounding_box()
   login=public_page.locator('.login-panel').bounding_box()
   submit=public_page.locator('#login-form [type="submit"]').bounding_box()
   assert headline['y']>=0 and headline['y']+headline['height']<=height,(width,headline)
   assert public_page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(appearance,width)
   assert submit['y']+submit['height']<=height,(width,submit)
   if width>1000:
    assert story['x']+story['width']<=login['x'],(story,login)
    assert story['y']<login['y']+login['height'] and login['y']<story['y']+story['height'],(story,login)
   else:assert login['y']>=headline['y']+headline['height']-1,(headline,login)
   public_page.screenshot(path=f'/tmp/sigin-hero-verified-{appearance}-{width}.png',full_page=True)
 assert surfaces['light']!=surfaces['dark'],'The login panel did not follow the selected theme'
 choose_theme(public_page,'system',guest=True)
 public_page.emulate_media(color_scheme='dark')
 expect(public_page.locator('html')).to_have_attribute('data-theme','dark')
 expect(public_page.locator('meta[name="theme-color"]')).to_have_attribute('content','#1c1817')
 public_page.emulate_media(color_scheme='light')
 expect(public_page.locator('html')).to_have_attribute('data-theme','light')
 expect(public_page.locator('meta[name="theme-color"]')).to_have_attribute('content','#f8f4ed')
 # Old browser data and controls inserted into the DOM must not grant access.
 public_page.evaluate("""() => localStorage.setItem('sigin-preview-v2', JSON.stringify({version:2,profile:{role:'teacher'},students:[],settings:[],attempts:[],practice:{}}))""")
 public_page.reload()
 public_page.locator('#login-form').wait_for()
 for action in ['home','myCourses','activities','activityMode','beginQuiz','course','lesson','admin','reviewAssessment','switchRole','preview']:
  public_page.evaluate("""action => {const b=document.createElement('button');b.dataset.action=action;b.dataset.course='gig-502';b.dataset.week='1';b.dataset.mode='assessment';b.textContent='Intentar acceso';document.querySelector('#app').append(b);} """,action)
  public_page.get_by_role('button',name='Intentar acceso').click()
  assert public_page.locator('#login-form').count()==1,action
  assert public_page.locator('.app-shell,.course-card,.context-card,#admin-course').count()==0,action
  public_page.locator('button').filter(has_text='Intentar acceso').evaluate_all('(buttons)=>buttons.forEach(b=>b.remove())')
 public_page.screenshot(path='/tmp/sigin-login-locked.png',full_page=True)
 # Restoring a token also requires server validation before the workspace opens.
 public_page.route('https://*.supabase.co/**',lambda route:route.fulfill(status=401,content_type='application/json',body='{"message":"JWT invalid"}'))
 public_page.evaluate("""() => sessionStorage.setItem('sigin-auth-session-v1', JSON.stringify({access_token:'forged',refresh_token:'forged',expires_at:9999999999,role:'teacher'}))""")
 public_page.reload()
 public_page.locator('#login-form').wait_for()
 assert public_page.locator('.app-shell,.course-card,#admin-course').count()==0
 assert public_page.locator('#login-error').inner_text()=='La sesión venció. Vuelve a ingresar.'
 assert public_page.evaluate("sessionStorage.getItem('sigin-auth-session-v1')")==None
 assert not public_errors,public_errors
 public_page.close()
 context=browser.new_context(viewport={'width':1440,'height':1000})
 config=(root/'assets/config.js').read_text()
 assert 'previewEnabled: false' in config
 context.route('**/assets/config.js',lambda route:route.fulfill(content_type='text/javascript',body=config.replace('previewEnabled: false','previewEnabled: true')))
 page=context.new_page()
 errors=[]
 page.on('pageerror',lambda e: errors.append(str(e)))
 page.on('dialog',lambda d:d.accept())
 page.goto(os.environ.get('SIGIN_TEST_URL','http://127.0.0.1:4173/'))
 # Use the same loaded module as the UI if authors refine text during validation.
 data=page.evaluate("async()=>{const {courses}=await import('./assets/courses.js');return courses;}")
 assert {q['type'] for c in data for a in c['activities'] for q in a['questions']}=={'choice','matching','ordering','crossword'}
 page.get_by_role('button',name='Explorar las tres materias').click()
 assert page.locator('.course-card').count()==3
 assert page.locator('main').bounding_box()['width']>1100
 page.screenshot(path='/tmp/sigin-home-desktop.png',full_page=True)
 def width_ok():assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),page.url
 captured_quizzes=set()
 def fill_answer(q,incorrect=False):
  if q['type']=='choice':page.locator('input[name="choice"][value="%s"]'%((q['correct']+1)%len(q['options']) if incorrect else q['correct'])).check()
  elif q['type']=='matching':
   for i,pair in enumerate(q['pairs']):
    right=q['pairs'][1-i]['right'] if incorrect and i<2 else pair['right']
    page.locator('.match-column').nth(0).locator('button').nth(i).click()
    page.locator('.match-column').nth(1).get_by_role('button').filter(has_text=right).click()
  elif q['type'] in ('ordering','order'):
   sequence=list(q['items'])
   if incorrect:sequence[0],sequence[1]=sequence[1],sequence[0]
   for target,text in enumerate(sequence):
    texts=page.locator('.order-text').evaluate_all("nodes=>nodes.map(node=>Array.from(node.childNodes).filter(child=>child.nodeType===Node.TEXT_NODE).map(child=>child.textContent).join(''))")
    current=texts.index(text)
    while current>target:
     page.locator('.order-item').nth(current).get_by_role('button').nth(0).click();current-=1
  elif q['type']=='crossword':
   for i in range(page.locator('.cw-input').count()):
    cell=page.locator('.cw-input').nth(i)
    ref=json.loads(cell.get_attribute('data-refs'))[0]
    cell.fill(word(q['entries'][ref['entry']]['word'])[ref['letter']])
   if incorrect:
    first=page.locator('.cw-input').first
    first.fill('Z' if first.input_value()!='Z' else 'Q')
 def feedback_controls(q,correct):
  kind={'choice':'.option','matching':'.match-item','ordering':'.order-item','order':'.order-item','crossword':'.cw-cell'}[q['type']]
  fields=page.locator('#quiz-answer '+kind)
  if q['type']=='choice':fields=fields.filter(has=page.locator('input:checked'))
  expected='correct' if correct else 'incorrect'
  assert fields.filter(has=page.locator('input:checked')).count()==1 if q['type']=='choice' else True
  assert fields.locator('xpath=self::*[contains(concat(" ",normalize-space(@class)," ")," '+expected+' ")]').count()>0,(q['id'],expected)
  if correct:
   assert fields.count()==page.locator('#quiz-answer '+kind+'.correct').count(),q['id']
   assert page.locator('#quiz-answer .incorrect').count()==0,q['id']
  elif q['type']!='choice':
   assert page.locator('#quiz-answer '+kind+'.correct').count()>0,'Mixed correct/incorrect parts should have individual feedback'
  else:
   assert page.locator('input[name="choice"][value="%s"]'%q['correct']).locator('..').evaluate("el=>el.classList.contains('correct')"),'Wrong selection should also identify the actual correct alternative'
  for status in ['correct','incorrect']:
   nodes=page.locator('#quiz-answer '+kind+'.'+status)
   for index in range(nodes.count()):
    colors=nodes.nth(index).evaluate("""el=>{const s=getComputedStyle(el);return [s.borderTopColor,s.backgroundColor].map(v=>v.match(/[\\d.]+/g).slice(0,3).map(Number));}""")
    assert any((rgb[1]>rgb[0] and rgb[1]>rgb[2]) if status=='correct' else (rgb[0]>rgb[1] and rgb[0]>rgb[2]) for rgb in colors),(q['id'],status,colors)
  if q['type']=='crossword':
   assert page.locator('#quiz-answer .cell-status').count()==page.locator('.cw-input').count()
   for cell in page.locator('.cw-input').all():
    assert re.search(r'; (?:Correcta|Incorrecta)$',cell.get_attribute('aria-label'))
    assert cell.get_attribute('aria-invalid') in ('true','false')
  else:assert page.locator('#quiz-answer .answer-status').count()>0,'Feedback needs text as well as color'
 def answer(q,assessment=False):
  page.set_viewport_size({'width':390,'height':900})
  fill_answer(q)
  dossier_panel=page.locator('.quiz-dossier')
  if dossier_panel.get_attribute('open') is None:dossier_panel.locator('summary').click()
  for appearance in ['light','dark']:
   page.emulate_media(color_scheme=appearance)
   expect(page.locator('html')).to_have_attribute('data-theme',appearance)
   for width in [360,1440]:
    page.set_viewport_size({'width':width,'height':1000})
    if not page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'):
     print('OVERFLOW',q['id'],q['type'],appearance,width)
     print(page.evaluate("Array.from(document.querySelectorAll('*')).filter(e=>e.getBoundingClientRect().right>window.innerWidth+1).map(e=>({tag:e.tagName,cl:e.className,right:e.getBoundingClientRect().right})).slice(-20)"))
     page.screenshot(path='/tmp/sigin-overflow.png',full_page=True)
    width_ok()
    assert page.locator('#quiz-answer').is_visible()
    reading=page.locator('.quiz-dossier .dossier')
    assert reading.evaluate('el=>el.scrollHeight<=el.clientHeight+1'),'Concepts/case clipped inside a nested scroller'
    for heading in (['Caso breve'] if assessment else ['Conceptos clave','Caso breve','Qué debes hacer']):
     assert reading.get_by_role('heading',name=re.compile('^'+re.escape(heading)+r'(?:\s*[:·—–-].*)?$',re.I)).is_visible()
    if assessment:
     assert page.locator('.reading-resources,.source-links,.hint,.feedback,.answer-status').count()==0
     assert reading.get_by_role('heading',name=re.compile('^Conceptos',re.I)).count()==0
     assert page.locator('#quiz-answer .correct,#quiz-answer .incorrect').count()==0
    if width==360:
     instructions=page.locator('.quiz-dossier .exam-instructions') if assessment else reading.get_by_role('heading',name=re.compile(r'^Qué debes hacer|^Instrucciones',re.I))
     instructions.scroll_into_view_if_needed()
     assert reading.evaluate('el=>el.scrollTop')==0
     assert page.locator('.quiz-grid > .context-card').evaluate('el=>el.scrollTop')==0
    screenshot_key=(q['type'],appearance,width)
    if screenshot_key not in captured_quizzes:
     page.evaluate("window.scrollTo({top:0,left:0,behavior:'instant'})")
     page.screenshot(path=f"/tmp/sigin-quiz-{q['type']}-{appearance}-{width}.png",full_page=True)
     captured_quizzes.add(screenshot_key)
  page.set_viewport_size({'width':1440,'height':1000})
 choose_theme(page,'system')
 for c in data:
  page.locator('.sidebar [data-action="activities"]').click()
  page.locator('#activity-course').select_option(c['id'])
  page.locator('[data-action="activityMode"][data-mode="practice"]').click()
  expect(page.locator('[data-action="activityMode"][data-mode="practice"]')).to_have_attribute('aria-pressed','true')
  page.locator('[data-action="beginQuiz"][data-week="1"][data-mode="practice"]').click()
  assert page.locator('.case-reading-note').is_visible()
  assert page.locator('.quiz-dossier').get_attribute('open') is not None
  for i,q in enumerate(c['activities'][0]['questions']):
   if c['id']==data[0]['id']:
    fill_answer(q,incorrect=True)
    page.get_by_role('button',name='Comprobar mi respuesta',exact=False).click()
    assert page.get_by_role('heading',name='Revisa el concepto y vuelve a intentarlo.').is_visible(),q['id']
    feedback_controls(q,False)
   answer(q)
   assert page.locator('#quiz-answer .correct,#quiz-answer .incorrect,.feedback,.answer-status').count()==0,'Changing an answer retained stale correctness feedback'
   page.get_by_role('button',name='Comprobar mi respuesta',exact=False).click()
   assert page.get_by_role('heading',name='Bien razonado.').is_visible(),q['id']
   if c['id']==data[0]['id']:feedback_controls(q,True)
   page.get_by_role('button',name='Revisar antes de terminar' if i==4 else 'Siguiente reto',exact=False).click()
  page.get_by_role('button',name='Confirmar y terminar').click()
  assert page.locator('.result-big').inner_text().startswith('10.0')
  page.locator('.side-nav').first.get_by_role('button',name='Inicio',exact=True).click()
 # Evaluate ALFIN first week, then view course-specific result.
 c=data[0]
 page.locator('.sidebar [data-action="activities"]').click()
 page.locator('#activity-course').select_option(c['id'])
 page.locator('[data-action="activityMode"][data-mode="assessment"]').click()
 closed=page.locator('[data-action="beginQuiz"][data-week="2"][data-mode="assessment"]')
 assert closed.is_disabled()
 page.evaluate("""() => {const b=document.createElement('button');b.dataset.action='beginQuiz';b.dataset.course='gig-502';b.dataset.week='2';b.dataset.mode='assessment';b.textContent='Intentar examen cerrado';document.querySelector('#app').append(b);} """)
 page.get_by_role('button',name='Intentar examen cerrado').click()
 expect(page.locator('#toast')).to_have_text('Esta evaluación está cerrada.')
 assert page.locator('#quiz-answer').count()==0
 page.locator('[data-action="beginQuiz"][data-week="1"][data-mode="assessment"]').click()
 for i,q in enumerate(c['activities'][0]['questions']):
  answer(q,assessment=True)
  page.get_by_role('button',name='Revisar antes de terminar' if i==4 else 'Siguiente reto',exact=False).click()
 page.get_by_role('button',name='Confirmar y terminar').click()
 assert page.locator('.result-big').inner_text().startswith('10.0')
 page.get_by_role('button',name='Ver como docente').click()
 page.get_by_role('button',name='Estudiantes',exact=True).click()
 assert page.get_by_role('heading',name='Estudiantes de la materia (0)').is_visible()
 with page.expect_download() as download:page.get_by_role('button',name='Descargar plantilla Excel').click()
 page.locator('#import-file').set_input_files(download.value.path())
 page.get_by_role('button',name='Confirmar filas válidas').wait_for()
 page.get_by_role('button',name='Confirmar filas válidas').click()
 assert page.get_by_role('heading',name='Estudiantes de la materia (1)').is_visible()
 page.get_by_role('button',name='Crear evaluación',exact=True).click()
 author_types=page.locator('select[data-author-type]')
 assert sorted(author_types.evaluate_all('(fields)=>fields.map(field=>field.value)'))==['choice','choice','crossword','matching','ordering']
 assert author_types.locator('option[value="numeric"]').count()==0
 author_types.first.select_option('crossword')
 assert page.get_by_text('Una palabra y pista por línea:',exact=False).first.is_visible()
 # Layout covers laptop, tablet and phone, including course overview.
 page.get_by_role('button',name='Ver como estudiante').click()
 app_surfaces={}
 for appearance in ['dark','light']:
  choose_theme(page,appearance)
  page.locator('.sidebar [data-action="home"]').click()
  app_surfaces[appearance]=page.locator('.course-card').first.evaluate('el=>getComputedStyle(el).backgroundColor')
  for selector in ['.side-nav button.active','.welcome-card h2','.welcome-card p','.course-content h3','.course-content p']:
   text_readable(page.locator(selector).first)
  for control in page.locator('button.primary, .course-content button').all():
   if control.is_visible():text_readable(control)
  for width in [1920,1440,1024,768,390,360]:
   page.set_viewport_size({'width':width,'height':900});width_ok()
   if width in [1440,360]:page.screenshot(path=f'/tmp/sigin-home-{appearance}-{width}.png',full_page=True)
 assert app_surfaces['light']!=app_surfaces['dark'],'The workspace did not follow the selected theme'
 page.set_viewport_size({'width':1440,'height':1000})
 page.locator('.sidebar [data-action="logout"]').click()
 expect(page.locator('html')).to_have_attribute('data-theme','light')
 page.reload();page.locator('#login-form').wait_for()
 expect(page.locator('html')).to_have_attribute('data-theme','light')
 assert not errors,errors
 print('PASS: minimal text hero + first-screen login laptop/phone; persistent themes and theme-color; readable controls and text; anonymous access closed; direct enrolled practice/exam; incorrect/correct controls red/green + text for four interaction types with retry clearing; assessment case without theory/resources/hints; Excel roundtrip; six widths; no JS errors')
 browser.close()
