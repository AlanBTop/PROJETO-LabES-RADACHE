/** Configuração pública. Não coloque chave de serviço, SMTP ou senha neste arquivo. */
export const CONFIG = Object.freeze({
  ambiente: 'local',
  apiBase: '/api/v1/',
  timeoutMs: 20000,
  revalidacaoMs: 60000,
});

export const PERFIS = Object.freeze({
  admin_tecnico:'Administrador Técnico',analista_institucional:'Analista Institucional',diretor_campus:'Diretor do Câmpus',gestor_curso:'Gestor de Curso',atendente_academico:'Atendente Acadêmico',
  admin_geral: 'Administração geral',
  coordenador_curso: 'Coordenação de curso',
  funcionario_curso: 'Funcionário de curso',
  caest: 'CAEst', prae: 'PRAE',
});

export const CATEGORIAS = Object.freeze({ academico: 'Acadêmico', financeiro: 'Financeiro', ti: 'TI', outro: 'Outro' });
export const STATUS = Object.freeze({ aberto: 'Aguardando atribuição', em_andamento: 'Em andamento', aguardando_aluno: 'Aguardando resposta do aluno', resolvido: 'Resolvido', encerrado: 'Encerrado', reaberto: 'Reaberto' });
export const TRANSICOES = Object.freeze({ aberto: ['em_andamento'], em_andamento: ['aguardando_aluno','resolvido'], aguardando_aluno: ['em_andamento', 'resolvido'], resolvido: ['reaberto','encerrado'], encerrado: ['reaberto'], reaberto: ['em_andamento','aguardando_aluno','resolvido'] });

/** Facilita a interface; a autorização efetiva continua no servidor e nas Rules. */
export function permissoes(perfil) {
  return Object.freeze({
    admin: ['admin_geral','admin_tecnico'].includes(perfil),
    gestor: ['admin_geral','admin_tecnico','gestor_curso','coordenador_curso'].includes(perfil),
    usuarios: ['admin_geral','admin_tecnico','gestor_curso','coordenador_curso','diretor_campus'].includes(perfil),
    transferir: ['admin_geral','admin_tecnico','diretor_campus'].includes(perfil),
    atendente: perfil === 'atendente_academico',
    equipe: ['admin_geral','admin_tecnico','diretor_campus','gestor_curso','coordenador_curso','funcionario_curso','atendente_academico'].includes(perfil),
    editarAluno: false,
  });
}
export const CAMPI={caceres:'Câmpus de Cáceres','varzea-grande':'Câmpus de Várzea Grande',cuiaba:'Câmpus de Cuiabá'};
