import assert from 'node:assert/strict'
import {mkdir,readFile,writeFile} from 'node:fs/promises'
import {chromium} from 'playwright'
const base='http://127.0.0.1:5173'
const out=process.env.SI12_EVIDENCE_DIR||'/tmp/si12-evidence'
await mkdir(out,{recursive:true})
const browser=await chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1920,height:1080},acceptDownloads:true})
const page=await context.newPage()
const errors=[]
page.on('pageerror',e=>errors.push(e.message))
const checks=[]
async function visible(locator){await locator.waitFor({state:'visible',timeout:20000})}
async function check(name,fn){await fn();checks.push(name)}
async function screenshot(name){await page.screenshot({path:out+'/'+name+'.png',fullPage:true})}
try{
  await check('real_health_and_blocked_gate',async()=>{
    const health=await context.request.get(base+'/api/v1/health')
    assert.equal(health.status(),200)
    const validation=await context.request.get(base+'/api/v1/validation/status')
    assert.equal(validation.status(),200)
    const d=await validation.json()
    assert.equal(d.pilot_ready,false);assert.equal(d.physical_actuation,false);assert.equal(d.operational_decision,'abstain')
  })
  await check('executive_and_videowall',async()=>{
    await page.goto(base+'/executivo')
    await visible(page.getByText('Piloto não homologado',{exact:true}))
    await screenshot('executive')
    await page.goto(base+'/videowall')
    await visible(page.getByText('Piloto não homologado',{exact:true}))
    await screenshot('videowall-1920')
    await page.getByRole('button',{name:'Sair do videowall'}).click()
    await page.waitForURL('**/executivo')
  })
  await check('operations_and_invalid_context',async()=>{
    await page.goto(base+'/operacional?intersection=UNKNOWN')
    await visible(page.getByText(/Cruzamento solicitado indisponível/))
    await visible(page.getByText('Piloto não homologado',{exact:true}))
    await screenshot('operations')
  })
  await check('laboratory_real_demo_and_archived_comparators',async()=>{
    await page.goto(base+'/laboratorio')
    await visible(page.getByText('Evidências experimentais arquivadas',{exact:true}))
    await visible(page.getByRole('table',{name:'Comparação científica arquivada'}))
    await visible(page.getByText('Proporcional apresentou menor espera',{exact:false}))
    await page.getByRole('button',{name:/SI-11B/}).click()
    await visible(page.getByText(/Menos ultrapassagens/))
    await page.getByRole('button',{name:/SI-11D/}).click()
    const downloadEvent=page.waitForEvent('download')
    await page.getByRole('button',{name:'Exportar extrato JSON'}).click()
    const download=await downloadEvent
    await download.saveAs(out+'/exported-evidence.json')
    const d=JSON.parse(await readFile(out+'/exported-evidence.json','utf8'))
    assert.equal(d.studies.length,4);assert.equal(d.physical_actuation,false)
    await visible(page.getByText(/Identificação reprodutível do resultado/))
    const first=await page.getByText(/Identificação reprodutível do resultado/).textContent()
    await page.reload()
    await visible(page.getByText(/Identificação reprodutível do resultado/))
    assert.equal(await page.getByText(/Identificação reprodutível do resultado/).textContent(),first)
    await screenshot('laboratory')
  })
  await check('pimcat_f_reports_and_research',async()=>{
    await page.goto(base+'/executivo')
    await visible(page.getByRole('heading',{name:'Relatório diário multimodal'}))
    await visible(page.getByText('Sem cruzamento para relatório',{exact:true}))
    await visible(page.getByRole('heading',{name:'Inteligência contínua — evidências'}))
    await page.goto(base+'/operacional?intersection=UNKNOWN')
    await visible(page.getByRole('heading',{name:'Relatório diário multimodal'}))
    await visible(page.getByRole('heading',{name:'Inteligência contínua — evidências'}))
    await page.goto(base+'/laboratorio')
    await visible(page.getByRole('table',{name:'Indicadores comparativos PIMCAT'}))
    await page.getByRole('button',{name:'PIMCAT C3',exact:true}).click()
    await visible(page.getByText(/Replay real externo — saídas do modelo/))
    await page.getByRole('button',{name:'240 s',exact:true}).click()
    await visible(page.getByText('Central indisponível — segmentos desconhecidos',{exact:true}))
    await visible(page.getByText('Desconhecido: 18',{exact:true}))
    const evt=page.waitForEvent('download')
    await page.getByRole('button',{name:'Exportar acervo PIMCAT'}).click()
    const dl=await evt;await dl.saveAs(out+'/pimcat-f-export.json')
    const e=JSON.parse(await readFile(out+'/pimcat-f-export.json','utf8'))
    assert.equal(e.studies.length,9);assert.equal(e.physical_actuation,false);assert.ok(e.suggestions.every(s=>s.applied===false))
    await screenshot('pimcat-f-laboratory')
  })
  await check('guided_seven_steps',async()=>{
    await page.goto(base+'/apresentacao')
    await visible(page.getByRole('navigation',{name:'Etapas da demonstração'}))
    const steps=page.getByRole('navigation',{name:'Etapas da demonstração'}).getByRole('button')
    assert.equal(await steps.count(),7)
    for(let i=0;i<7;i++){
      await steps.nth(i).click()
      await visible(page.getByText('Passo '+(i+1)+' de 7',{exact:false}))
    }
    await visible(page.getByText('Piloto não homologado',{exact:true}))
    await steps.nth(5).click()
    await visible(page.getByText('Evidências experimentais arquivadas',{exact:true}))
    await screenshot('presentation')
  })
  await check('homologation_no_false_ready',async()=>{
    await page.goto(base+'/homologacao')
    await visible(page.getByText('Ainda não aprovado para piloto',{exact:true}))
    await screenshot('validation')
    await page.route('**/api/v1/validation/status',r=>r.fulfill({status:503,body:'unavailable'}))
    await page.reload()
    await visible(page.getByText('Homologação indisponível',{exact:true}))
    await page.unroute('**/api/v1/validation/status')
  })
  await check('mobile_no_page_overflow',async()=>{
    await page.setViewportSize({width:390,height:844})
    await page.goto(base+'/laboratorio')
    await visible(page.getByText('Evidências experimentais arquivadas',{exact:true}))
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+2))
    await screenshot('mobile-laboratory')
  })
  assert.deepEqual(errors,[])
  await writeFile(out+'/browser-results.json',JSON.stringify({scope:'local_synthetic_product_demo',checks,passed:true,page_errors:errors,physical_actuation:false,field_validation:false},null,2))
}finally{await browser.close()}
