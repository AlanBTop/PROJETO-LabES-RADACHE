import { CHECKIN_TEXTOS as T } from '../data/checkin-textos.js';

const PENDENTES = new Set(['consentimento', 'aguardando_inicio', 'financeira', 'emocional']);
const TEMPLATES = { boasVindas: 'radache_boas_vindas', mensal: 'radache_mensal', lembrete: 'radache_lembrete' };
const MES = instante => {
  const data = new Date(instante);
  return data.getFullYear() + '-' + String(data.getMonth() + 1).padStart(2, '0');
};
const texto = (chave, rotulo = '') => ({ texto: T[chave], rotulo, template: TEMPLATES[chave] || null });

/** Soma meses de calendário, limitando o dia ao último do mês (29/02 → 28/02). */
function somarMeses(instante, quantidade, diaPreferido = new Date(instante).getDate()) {
  const data = new Date(instante);
  data.setDate(1);
  data.setMonth(data.getMonth() + quantidade);
  const ultimoDia = new Date(data.getFullYear(), data.getMonth() + 1, 0).getDate();
  data.setDate(Math.min(diaPreferido, ultimoDia));
  return data.getTime();
}

/**
 * Máquina de estados do roteiro acadêmico, sem DOM, HTTP ou banco.
 * Guarda consentimento e sua data por aluno na memória da aba; a validade usa
 * 12 meses de calendário, com vencimento inclusivo, não uma aproximação em dias.
 */
export class CheckinSimulator {
  constructor(agora = () => Date.now()) {
    this.agora = agora;
    this.sessoes = new Map();
  }

  reiniciar(id) {
    const instante = this.agora();
    this.sessoes.set(id, {
      etapa: 'consentimento', consentimento: false, dataConsentimento: null,
      financeira: null, emocional: null, concluidoMes: null,
      instante, diaCalendario: new Date(instante).getDate(), ultimaInteracao: instante, lembreteEnviado: false,
    });
    return this.abrirCiclo(this.sessoes.get(id));
  }

  consentimentoValido(s) {
    return s.consentimento && s.dataConsentimento !== null &&
      s.instante < somarMeses(s.dataConsentimento, 12);
  }

  /** Escolhe um dos dois convites; o mensal não renova a autorização anual. */
  abrirCiclo(s) {
    const valido = this.consentimentoValido(s);
    Object.assign(s, {
      etapa: valido ? 'aguardando_inicio' : 'consentimento', consentimento: valido,
      financeira: null, emocional: null, concluidoMes: null,
      ultimaInteracao: s.instante, lembreteEnviado: false,
    });
    return valido ? [texto('mensal', 'radache_mensal · simulado')] :
      [texto('boasVindas', 'radache_boas_vindas · simulado')];
  }

  /** Snapshot da data de autorização/validade e componentes; não calcula o RE total. */
  estado(id) {
    const s = this.sessoes.get(id);
    if (!s) throw new Error('Inicie a sessão simulada antes de responder.');
    const vencimento = s.dataConsentimento === null ? null : somarMeses(s.dataConsentimento, 12);
    return {
      ...s,
      consentimento: this.consentimentoValido(s),
      dataConsentimento: s.dataConsentimento === null ? null : new Date(s.dataConsentimento).toISOString(),
      validadeConsentimento: vencimento === null ? null : new Date(vencimento).toISOString(),
      consentimentoExpirado: vencimento !== null && s.instante >= vencimento,
      timestamp: new Date(s.instante).toISOString(), mes: MES(s.instante),
      F: s.financeira === null ? null : [0, 33, 66, 100][s.financeira - 1],
      P: s.emocional === null ? null : ((5 - s.emocional) / 4) * 100,
    };
  }

  /**
   * Processa uma mensagem do aluno. A resposta 1 às boas-vindas autoriza por
   * 12 meses; a resposta 1 ao mensal só inicia as perguntas, sem renovar a data.
   * Todas as respostas de texto livre são produzidas nesta interação do aluno.
   * @param {number} id Identificador fictício do aluno.
   * @param {string} conteudo Texto recebido.
   * @param {'texto'|'audio'} tipo Tipo de interação simulada.
   * @returns {{mensagens: Object[], sensivel: boolean, revogado: boolean}}
   */
  responder(id, conteudo, tipo = 'texto') {
    const s = this.sessoes.get(id);
    s.ultimaInteracao = s.instante;
    const saida = mensagens => ({ mensagens, sensivel: false, revogado: false });
    if (tipo !== 'texto') return saida([texto('naoTexto')]);
    const comando = conteudo.trim().toUpperCase();
    if (comando === 'REVOGAR') {
      Object.assign(s, {
        etapa: 'revogado', consentimento: false, dataConsentimento: null,
        financeira: null, emocional: null, concluidoMes: null,
      });
      return { mensagens: [texto('revogacao')], sensivel: false, revogado: true };
    }
    // Uma resposta da etapa antiga não pode aceitar a renovação implicitamente.
    if (!this.consentimentoValido(s) && ['aguardando_inicio', 'financeira', 'emocional', 'concluido'].includes(s.etapa)) {
      return saida(this.abrirCiclo(s));
    }
    if (s.concluidoMes === MES(s.instante)) return saida([texto('respondido')]);
    if (s.etapa === 'concluido') return saida(this.abrirCiclo(s));
    if (comando === 'INICIAR') {
      if (['financeira', 'emocional'].includes(s.etapa)) return saida([texto(s.etapa)]);
      return saida(this.abrirCiclo(s));
    }
    if (s.etapa === 'recusado') return saida([texto('recusa')]);
    if (s.etapa === 'revogado') return saida([texto('revogacao')]);
    if (s.etapa === 'consentimento') {
      if (comando === '1') {
        s.consentimento = true;
        s.dataConsentimento = s.instante;
        s.etapa = 'financeira';
        return saida([texto('financeira')]);
      }
      if (comando === '2') {
        Object.assign(s, { etapa: 'recusado', consentimento: false, dataConsentimento: null });
        return saida([texto('recusa')]);
      }
    } else if (s.etapa === 'aguardando_inicio' && comando === '1') {
      s.etapa = 'financeira';
      return saida([texto('financeira')]);
    } else if (s.etapa === 'financeira' && /^[1-4]$/.test(comando)) {
      s.financeira = Number(comando);
      s.etapa = 'emocional';
      return { mensagens: [texto('emocional')], sensivel: true, revogado: false };
    } else if (s.etapa === 'emocional' && /^[1-5]$/.test(comando)) {
      s.emocional = Number(comando);
      s.etapa = 'concluido';
      s.concluidoMes = MES(s.instante);
      return { mensagens: [texto('encerramento')], sensivel: true, revogado: false };
    }
    const pergunta = { consentimento: 'boasVindas', aguardando_inicio: 'mensal', financeira: 'financeira', emocional: 'emocional' }[s.etapa];
    return saida([texto('invalida'), texto(pergunta)]);
  }

  /** Avança 72 horas; no vencimento, a renovação substitui o lembrete comum. */
  avancarTresDias(id) {
    const s = this.sessoes.get(id);
    const estavaValido = this.consentimentoValido(s);
    s.instante += 3 * 86400000;
    s.diaCalendario = new Date(s.instante).getDate();
    if (estavaValido && !this.consentimentoValido(s)) return this.abrirCiclo(s);
    if (!PENDENTES.has(s.etapa) || s.lembreteEnviado || s.instante - s.ultimaInteracao < 3 * 86400000) return [];
    s.lembreteEnviado = true;
    return [texto('lembrete', 'radache_lembrete · após 3 dias · simulado')];
  }

  /** Mantém o dia/horário ao avançar o calendário e seleciona o template correto. */
  avancarMeses(id, quantidade) {
    const s = this.sessoes.get(id);
    s.instante = somarMeses(s.instante, quantidade, s.diaCalendario);
    return this.abrirCiclo(s);
  }

  proximoMes(id) { return this.avancarMeses(id, 1); }

  avancarDozeMeses(id) { return this.avancarMeses(id, 12); }
}
