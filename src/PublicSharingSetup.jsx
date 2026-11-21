import React,{useEffect,useState} from 'react';
import {Check,ChevronRight,RefreshCw} from 'lucide-react';

export default function PublicSharingSetup({backendOrigin}){
 const [opened,setOpened]=useState(false),[step,setStep]=useState(0),[status,setStatus]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [accountReady,setAccountReady]=useState(false),[domain,setDomain]=useState(()=>localStorage.getItem('dc-public-domain-draft')||'');
 const stages=['Verificar requisitos','Conta Cloudflare','Escolher domínio','Instalar conector','Configurar túnel','Verificar e ativar'];
 const install=status?.installation||{};
 const running=['starting','release','download','verify'].includes(install.stage);
 async function refresh(){
  try{
   const r=await fetch(backendOrigin+'/api/public-setup/status',{cache:'no-store'});
   if(!r.ok)throw Error('Não foi possível verificar a instalação.');
   setStatus(await r.json());
  }catch(e){setError(e.message)}
 }
 useEffect(()=>{refresh()},[]);
 useEffect(()=>{
  if(!opened||!running)return;
  const timer=setInterval(refresh,750);
  return()=>clearInterval(timer);
 },[opened,running]);
 async function installConnector(){
  setBusy(true);setError('');
  try{
   const r=await fetch(backendOrigin+'/api/public-setup/install',{method:'POST'});
   const data=await r.json().catch(()=>({}));
   if(!r.ok)throw Error(data.detail||'Falha ao instalar conector.');
   await refresh();
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 const domainValid=/^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i.test(domain.trim());
 const canNext=[!!status?.supported,accountReady,domainValid,!!status?.installed,false,false][step];
 return <div className="dc-module-section dc-public-setup">
  <h3>Compartilhamento público (opcional)</h3>
  <p>Publique arquivos para pessoas sem Telegram usando um domínio próprio. Nada será instalado ou exposto até você autorizar.</p>
  {!opened?<button className="dc-module-primary" onClick={()=>setOpened(true)}>Configurar compartilhamento</button>:<>
   <div className="dc-public-steps">{stages.map((name,i)=><span key={name} className={i===step?'current':i<step?'done':''}>{i+1}. {name}</span>)}</div>
   <div className="dc-public-stage">
    <strong>Etapa {step+1} de 6 — {stages[step]}</strong>
    {step===0&&<><p>Verificamos o sistema operacional e a compatibilidade antes de qualquer instalação.</p><p>{status?status.system+' — '+(status.supported?'Compatível':'Não compatível com instalação automática'):'Verificando...'}</p><button onClick={refresh}>Verificar novamente</button></>}
    {step===1&&<><p>Crie uma conta na Cloudflare e adicione seu domínio. O Drive Cloud não solicita senhas da Cloudflare.</p><a href="https://dash.cloudflare.com/" target="_blank" rel="noopener noreferrer">Abrir Cloudflare Dashboard</a><label className="dc-public-check"><input type="checkbox" checked={accountReady} onChange={e=>setAccountReady(e.target.checked)}/> Já tenho domínio gerenciado na Cloudflare.</label><small>Esta etapa é uma confirmação manual, não uma autorização de API.</small></>}
    {step===2&&<><p>Escolha o endereço público que deseja configurar.</p><label className="dc-new-remote-folder-name">Domínio ou subdomínio<input value={domain} onChange={e=>{setDomain(e.target.value.toLowerCase());localStorage.setItem('dc-public-domain-draft',e.target.value.toLowerCase())}} placeholder="arquivos.seudominio.com.br"/></label><small>O DNS ainda não será alterado.</small></>}
    {step===3&&<><p>Autorize o download do conector oficial da Cloudflare. O Drive Cloud confere o SHA-256 antes de instalar. Nenhum túnel é iniciado automaticamente.</p>{status?.installed?<p className="dc-public-good"><Check size={16}/> Conector instalado.</p>:<button type="button" className="dc-module-primary" onClick={installConnector} disabled={busy||running||!status?.supported}> {running?'Instalando...':'Autorizar e instalar conector'}</button>}{install.stage!=='idle'&&<><div className="dc-public-progress"><span style={{width:(install.percent||0)+'%'}}/></div><small>{install.percent||0}% — {install.detail}</small></>}{install.error&&<p className="public-share-error">{install.error}</p>}</>}
    {step===4&&<p className="public-share-error">Etapa protegida: falta implementar o gateway público isolado e a autorização de criação do túnel. Não aponte um túnel para o backend local atual, pois ele contém rotas administrativas privadas.</p>}
    {step===5&&<p>O compartilhamento só será ativado depois de testar o HTTPS, os links públicos e os controles de acesso. Ainda não disponível.</p>}
   </div>
   {error&&<p className="public-share-error">{error}</p>}
   <div className="dc-public-controls"><button onClick={()=>step===0?setOpened(false):setStep(n=>n-1)}>{step===0?'Fechar':'Anterior'}</button>{step<4&&<button className="dc-module-primary" onClick={()=>setStep(n=>n+1)} disabled={!canNext||running}>Próximo <ChevronRight size={16}/></button>}</div>
  </>}
 </div>;
}
