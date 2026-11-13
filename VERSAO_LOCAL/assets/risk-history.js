/* Componente compartilhado por atendimento e perfil analítico. Dados vêm do backend. */
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=String(text);return n;};
const fmt=n=>Number(n).toLocaleString('pt-BR',{maximumFractionDigits:2});
const date=s=>{const d=new Date(String(s).replace(' ','T'));return Number.isNaN(d.getTime())?'Data não informada':d.toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'});};
const origins={whatsapp_simulado:'WhatsApp simulado',whatsapp_checkin:'Questionário WhatsApp',registro_academico:'Registro acadêmico',avaliacao_informada:'Avaliação informada',povoamento_demonstrativo:'Dados fictícios de demonstração'};
const colors={aumentou:'#b4233d',diminuiu:'#15803d',estavel:'#64748b',inicial:'#173e74'};
export function changeLabel(data){
  if(!data||data.variacao==null)return data?.direcao==='sem_avaliacao'?'Sem avaliação válida':'Sem avaliação anterior para comparar';
  return data.variacao===0?'Risco estável':`${data.variacao>0?'Aumentou':'Diminuiu'} ${fmt(Math.abs(data.variacao))} pontos`;
}

export function renderRiskHistory(data){
  const d=data||{pontos:[],avaliacoes:[]},root=node('section','risk-history-section');
  root.setAttribute('aria-label','Evolução do risco acadêmico');
  root.append(node('h3','','Evolução do risco acadêmico'),node('p','risk-independence','Atendimento e risco são independentes. Iniciar ou concluir um atendimento não reduz o índice.'));
  const summary=node('div','risk-history-summary');
  for(const [label,value] of [['Risco inicial',d.inicial==null?'Sem avaliação':fmt(d.inicial)+' / 100'],['Risco atual',d.atual==null?'Sem avaliação':fmt(d.atual)+' / 100'],['Última variação',changeLabel(d)]]){
    const card=node('div');card.append(node('span','',label),node('strong','',value));summary.append(card);
  }
  root.append(summary);
  const points=d.pontos||[];
  if(points.length){
    // Ordem das avaliações, sem estimar amostras ou preencher períodos sem dados.
    const shown=points.slice(-60),width=Math.max(520,shown.length*48),height=220,left=44,right=25,top=20,bottom=45;
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.style.width=width+'px';svg.setAttribute('role','img');
    svg.setAttribute('aria-label',`Evolução do índice: ${shown.map(p=>`${date(p.data)}, ${fmt(p.indice)} de 100`).join('; ')}`);
    const add=(tag,attrs,text)=>{const n=document.createElementNS(svg.namespaceURI,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!=null)n.textContent=text;svg.append(n);return n;};
    const x=i=>shown.length===1?(width+left-right)/2:left+i*(width-left-right)/(shown.length-1),y=v=>top+(100-v)*(height-top-bottom)/100;
    for(const tick of [0,33,67,100]){add('line',{x1:left,x2:width-right,y1:y(tick),y2:y(tick),stroke:'#dfe6ef','stroke-dasharray':'3 4'});add('text',{x:left-9,y:y(tick)+4,'text-anchor':'end',fill:'#61718b','font-size':11},tick);}
    shown.forEach((p,i)=>{
      if(i)add('line',{x1:x(i-1),y1:y(shown[i-1].indice),x2:x(i),y2:y(p.indice),stroke:colors[p.direcao]||colors.inicial,'stroke-width':2.5});
      const circle=add('circle',{cx:x(i),cy:y(p.indice),r:4,fill:colors[p.direcao]||colors.inicial,stroke:'white','stroke-width':1.5});
      const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=`${date(p.data)} · Índice ${fmt(p.indice)} / 100`;circle.append(title);
      if(i===0||i===shown.length-1||i%Math.max(1,Math.ceil(shown.length/6))===0)add('text',{x:x(i),y:height-19,'text-anchor':i===0?'start':i===shown.length-1?'end':'middle',fill:'#61718b','font-size':10},new Date(String(p.data).replace(' ','T')).toLocaleDateString('pt-BR'));
    });
    const scroll=node('div','risk-history-plot');scroll.tabIndex=0;scroll.setAttribute('aria-label','Gráfico de evolução; histórico detalhado a seguir');scroll.append(svg);root.append(scroll);
    root.append(node('p','risk-history-note',points.length<2?'Uma avaliação válida: ainda não há comparação disponível.':`${shown.length} avaliações em ordem cronológica, com espaçamento uniforme. Passe sobre os pontos para ver data e índice.${points.length>60?' O gráfico mostra as últimas 60; a lista preserva todo o histórico.':''}`));
  }else root.append(node('p','risk-history-note','Sem avaliação numérica válida. Nenhuma evolução foi estimada.'));
  const details=node('details','risk-history-records'),heading=node('summary','',`Histórico e fatores de variação (${(d.avaliacoes||[]).length} avaliações)`);details.append(heading);
  for(const e of [...(d.avaliacoes||[])].reverse()){
    const record=node('article','risk-history-record');record.append(node('strong','',date(e.data)),node('span','risk-history-source',origins[e.origem]||'Registro acadêmico'));
    record.append(node('p','',e.indice==null?'Sem índice válido':`Índice ${fmt(e.indice)} / 100 · ${changeLabel({direcao:e.direcao,variacao:e.variacao_pontos})}`));
    if(e.fatores?.length){const list=node('ul');for(const f of e.fatores){const suffix=f.chave==='frequencia'?'%':f.chave==='notas'?' / 10':'';list.append(node('li','',`${f.nome}: ${f.anterior}${suffix} → ${f.atual}${suffix}.${f.variacao_contribuicao!=null?` Contribuição no índice: ${f.variacao_contribuicao>0?'+':''}${fmt(f.variacao_contribuicao)} pontos.`:` Componente de risco: ${fmt(f.componente_anterior)} → ${fmt(f.componente_atual)} / 100.`}`));}record.append(list);}
    if(e.variacao_pontos!=null&&!e.comparacao_completa)record.append(node('small','','Comparação parcial: o registro anterior não contém todos os componentes e pesos.'));
    if(e.pesos_alterados)record.append(node('small','','Os pesos da fórmula mudaram entre estas avaliações; a variação não representa apenas mudança nas respostas.'));
    details.append(record);
  }
  root.append(details,node('p','risk-history-note',d.nota||'O índice é uma pontuação de acompanhamento, não uma probabilidade validada de evasão.'));
  return root;
}
