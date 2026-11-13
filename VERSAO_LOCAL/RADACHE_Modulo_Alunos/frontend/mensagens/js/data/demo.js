/** Dados exclusivamente fictícios; estes IDs não referenciam o banco de alunos. */
export const CONTATOS_DEMO = [
  { id: 101, nome: 'Ana Martins', iniciais: 'AM', curso: 'Ciência da Computação', semestre: '4º semestre', tom: 'sage', naoLidas: 0 },
  { id: 102, nome: 'Lucas Silva', iniciais: 'LS', curso: 'Engenharia de Software', semestre: '3º semestre', tom: 'sand', naoLidas: 2 },
  { id: 103, nome: 'Beatriz Almeida', iniciais: 'BA', curso: 'Pedagogia', semestre: '6º semestre', tom: 'rose', naoLidas: 1 },
  { id: 104, nome: 'Rafael Costa', iniciais: 'RC', curso: 'Administração', semestre: '2º semestre', tom: 'blue', naoLidas: 0 },
  { id: 105, nome: 'Camila Oliveira', iniciais: 'CO', curso: 'Direito', semestre: '5º semestre', tom: 'lilac', naoLidas: 0 },
  { id: 106, nome: 'Pedro Santos', iniciais: 'PS', curso: 'Ciências Contábeis', semestre: '4º semestre', tom: 'teal', naoLidas: 0 },
];

function mensagem(id, texto, hora, enviada = false) {
  const instante = new Date();
  instante.setHours(hora[0], hora[1], 0, 0);
  return { id, texto, timestamp: instante.toISOString(), enviada, status: 'exemplo', payload: null };
}

/** Retorna um novo histórico por conversa; nenhuma leitura de banco é executada. */
export function criarHistoricosDemo() {
  return new Map([
    [101, [
      mensagem('ana-1', 'Olá, Ana! Tudo bem? 👋\nSou da equipe de acompanhamento do RADACHE.', [9, 30], true),
      mensagem('ana-2', 'Oi! Tudo bem, sim. Como posso ajudar?', [9, 32]),
      mensagem('ana-3', 'Estamos acompanhando como está sendo o semestre. Como estão as aulas e a sua rotina de estudos?', [9, 33], true),
      mensagem('ana-4', 'As aulas estão indo bem! Estou organizando melhor meus horários para acompanhar as atividades. 😊', [9, 35]),
      mensagem('ana-5', 'Que bom saber! Se precisar de algum apoio, pode contar com a gente. 💚', [9, 36], true),
      mensagem('ana-6', 'Muito obrigada pela atenção! Vou avisando por aqui.', [9, 38]),
    ]],
    [102, [mensagem('lucas-1', 'Olá, Lucas! Como está o semestre?', [9, 25], true), mensagem('lucas-2', 'Bom dia! Estou me organizando por aqui.', [9, 40]), mensagem('lucas-3', 'Podemos conversar sobre os horários de atendimento?', [9, 41])]],
    [103, [mensagem('bia-1', 'Olá, Beatriz! Podemos ajudar em algo?', [9, 10], true), mensagem('bia-2', 'Olá! Gostaria de saber mais sobre a monitoria.', [9, 22])]],
    [104, [mensagem('rafael-1', 'Rafael, o atendimento está confirmado para amanhã.', [8, 55], true), mensagem('rafael-2', 'Combinado, até amanhã! 👍', [9, 2])]],
    [105, [mensagem('camila-1', 'Obrigada! Já consegui acessar as atividades.', [8, 40]), mensagem('camila-2', 'Perfeito, Camila. Seguimos à disposição!', [8, 45], true)]],
    [106, [mensagem('pedro-1', 'Olá, Pedro! Seja bem-vindo ao acompanhamento RADACHE. 🎓', [8, 20], true), mensagem('pedro-2', 'Bom dia! Obrigado pelo contato.', [8, 23])]],
  ]);
}
