"""Integração SQLite da gestão local: isolamento, persistência, permissões e ações."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
import gestao_local as gestao
import simulation_store as store


class GestaoLocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.anterior = database.DB_PATH
        self.simulation_paths = store.ACADEMIC, store.OPERATIONAL
        database.DB_PATH = Path(self.temp.name) / 'gestao.db'
        store.ACADEMIC = Path(self.temp.name) / 'mock_sigaa.db'
        store.OPERATIONAL = Path(self.temp.name) / 'radache.db'
        store.init()
        database.init_db()
        gestao.iniciar()
        gestao.SESSOES.clear()
        self.token = self.login('admin')

    def tearDown(self):
        database.DB_PATH = self.anterior
        store.ACADEMIC, store.OPERATIONAL = self.simulation_paths
        gestao.SESSOES.clear()
        self.temp.cleanup()

    def login(self, nome):
        return gestao.tratar('POST', 'login', {}, {'email': nome + '@radache.local', 'senha': 'admin123'}, '')['token']

    def api(self, method, path, body=None, query=None, token=None):
        return gestao.tratar(method, path, query or {}, body or {}, token or self.token)

    def test_migracao_idempotente_preserva_dados_e_cadastros_compartilhados(self):
        original = database.list_alunos()
        gestao.iniciar()
        self.assertEqual(original, database.list_alunos())
        for method,path in [('POST','alunos'),('PATCH','alunos/1')]:
            with self.assertRaises(gestao.ErroLocal) as error:
                self.api(method,path,{'nome':'Aluno local'})
            self.assertEqual(error.exception.status,405)
        self.assertEqual(original,database.list_alunos())

    def test_login_senha_logout_e_escopo_de_curso(self):
        with self.assertRaises(gestao.ErroLocal) as erro:
            self.api('POST', 'login', {'email': 'admin@radache.local', 'senha': 'errada'})
        self.assertEqual(erro.exception.status, 401)
        coord = self.login('coord')
        lista = self.api('GET', 'alunos', token=coord)['itens']
        self.assertTrue(lista)
        self.assertTrue(all(a['cursoId'] == 'ciencia-da-computacao' for a in lista))
        outro = next(a for a in self.api('GET', 'alunos')['itens'] if a['cursoId'] != 'ciencia-da-computacao')
        with self.assertRaises(gestao.ErroLocal):
            self.api('GET', 'alunos/' + outro['id'], token=coord)
        equipe = self.api('GET', 'usuarios', token=self.login('equipe'))['itens']
        self.assertTrue(all(u['perfil'] == 'atendente_academico' and u['campusId'] == 'caceres' and 'ciencia-da-computacao' in u['cursoIds'] for u in equipe))
        with self.assertRaises(gestao.ErroLocal):
            self.api('GET', 'alunos', token=self.login('caest'))
        self.api('POST', 'logout', token=coord)
        with self.assertRaises(gestao.ErroLocal):
            self.api('GET', 'sessao', token=coord)

    def test_usuario_persistente_desativacao_revoga_sessao(self):
        item = self.api('POST', 'usuarios', {'nome': 'Equipe teste', 'email': 'teste@radache.local', 'senhaInicial': 'admin123', 'perfil': 'atendente_academico', 'campusId': 'caceres', 'cursoIds': ['direito']})
        token = self.login('teste')
        self.assertEqual(self.api('GET', 'sessao', token=token)['nome'], 'Equipe teste')
        gestao.iniciar()
        self.assertEqual(self.api('GET', 'usuarios/' + item['id'])['email'], 'teste@radache.local')
        self.api('PATCH', 'usuarios/' + item['id'], {'ativo': False})
        with self.assertRaises(gestao.ErroLocal):
            self.api('GET', 'sessao', token=token)
        with self.assertRaises(gestao.ErroLocal):
            self.login('teste')

    def test_chamado_historico_idempotencia_e_transicoes(self):
        item = self.api('GET', 'atendimentos', query={'status': 'aberto'})['itens'][0]
        caminho = 'atendimentos/' + item['id']
        dados = {'idAcao': 'acao1', 'texto': 'Atendimento realizado.', 'visivelAoAluno': True}
        primeiro = self.api('POST', caminho + '/comentarios', dados)
        self.assertEqual(primeiro, self.api('POST', caminho + '/comentarios', dados))
        self.assertEqual(len(self.api('GET', caminho + '/historico')['itens']), 2)
        with self.assertRaises(gestao.ErroLocal):
            self.api('POST', caminho + '/comentarios', {**dados, 'texto': 'Outro texto'})
        with self.assertRaises(gestao.ErroLocal):
            self.api('POST', caminho + '/status', {'idAcao': 'errada', 'status': 'resolvido', 'texto': 'Pular estados'})
        with self.assertRaises(gestao.ErroLocal) as erro:
            self.api('POST', caminho + '/status', {'idAcao': 'sem-responsavel', 'status': 'em_andamento', 'texto': 'Tentativa sem responsável.'})
        self.assertEqual(erro.exception.status, 409)
        aluno = self.api('GET', 'alunos/' + item['alunoId'])
        atendente = self.api('POST', 'usuarios', {'nome': 'Atendente teste', 'login': 'atendente-teste', 'senhaInicial': 'Inicial#2026', 'perfil': 'atendente_academico', 'campusId': 'caceres', 'cursoIds': [aluno['cursoId']]})
        assigned = self.api('POST', caminho + '/responsavel', {'idAcao': 'atribuir', 'uid': atendente['id'], 'texto': 'Atribuição inicial de teste.'})
        self.assertEqual(assigned['status'], 'em_andamento')
        for i, status in enumerate(['aguardando_aluno', 'resolvido']):
            self.api('POST', caminho + '/status', {'idAcao': str(i), 'status': status, 'texto': 'Etapa concluída'})
        gestao.iniciar()
        self.assertEqual(self.api('GET', caminho)['status'], 'resolvido')
        self.assertEqual(len(self.api('GET', caminho + '/historico')['itens']), 5)

    def test_rotas_invalidas_e_paginacao(self):
        pagina = self.api('GET', 'alunos', query={'limite': '2'})
        self.assertEqual(len(pagina['itens']), 2)
        proxima = self.api('GET', 'alunos', query={'limite': '2', 'depois': pagina['proximaPagina']})
        self.assertNotEqual(pagina['itens'][0]['id'], proxima['itens'][0]['id'])
        with self.assertRaises(gestao.ErroLocal) as erro:
            self.api('PATCH', 'usuarios/coord/extra', {'ativo': False})
        self.assertEqual(erro.exception.status, 404)


if __name__ == '__main__':
    unittest.main()
