/** Catálogo compartilhado pelos simuladores JS e SQLite; nenhum envio à Meta. */
export const CHECKIN_TEXTOS = Object.freeze({
  boasVindas: `Este check-in do RADACHE é uma simulação de duas perguntas para orientar o apoio ao estudante.`,
  privacidade: `As perguntas são sobre sua situação financeira e como você tem se sentido.
Só a equipe de apoio acessa suas respostas; sua autorização vale por 12 meses.`,
  sair: `Participar é opcional; envie SAIR a qualquer momento para recusar ou revogar e apagar suas respostas.`,
  consentimento: `Você aceita participar desta simulação?
1 - Aceito
2 - Recuso
Responda apenas com o número da opção.
Para sair: SAIR`,
  mensal: `Você quer responder ao check-in simulado deste mês?
1 - Começar
2 - Recuso
Responda apenas com o número da opção.
Para sair: SAIR`,
  lembrete: `Seu check-in simulado está pendente; a pergunta será repetida abaixo.
Para encerrar sua participação, envie SAIR.`,
  financeira: `Pergunta 1 de 2 — Situação financeira
Hoje, como estão suas condições financeiras para continuar estudando?
1 - Sem dificuldade
2 - Dificuldade leve
3 - Dificuldade significativa
4 - Penso em trancar o curso por motivo financeiro
Responda apenas com o número da opção.
Para sair: SAIR`,
  emocional: `Pergunta 2 de 2 — Bem-estar emocional
Nas últimas semanas, como você tem se sentido?
1 - Muito ruim
2 - Ruim
3 - Regular
4 - Bom
5 - Muito bom
Responda apenas com o número da opção.
Para sair: SAIR`,
  apoio: `Se precisar de apoio, procure a equipe de apoio ao estudante da UNEMAT.
O CVV atende 24 horas pelo telefone 188.`,
  encerramento: `Obrigado, suas respostas foram registradas nesta simulação.
A análise serve de apoio e não substitui a orientação de profissionais.`,
  recusa: `Participação recusada; nenhuma resposta deste check-in foi registrada.
Para tentar de novo, envie INICIAR.`,
  revogacao: `Participação cancelada e respostas apagadas.
Para tentar de novo, envie INICIAR.`,
  invalida: `Responda apenas com o número da opção.`,
  encerradoInvalido: `Obrigado pelo seu tempo; o check-in foi encerrado sem registrar respostas incompletas.
Para tentar de novo, envie INICIAR.`,
  respondido: `Suas respostas deste mês já foram registradas nesta simulação.
Para revogar e apagar suas respostas, envie SAIR.`,
  naoTexto: `Envie uma mensagem de texto com apenas o número da opção.`,
});
