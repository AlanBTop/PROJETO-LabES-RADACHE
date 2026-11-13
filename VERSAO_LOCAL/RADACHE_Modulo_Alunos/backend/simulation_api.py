"""Rotas locais; somente a coordenação pode escrever no cadastro acadêmico."""
import re
import sqlite3
from urllib.parse import urlsplit
import simulation_store as store
import rbac


def respond(handler):
    path=urlsplit(handler.path).path.rstrip('/')
    admin=path.startswith('/api/mock-alunos')
    if not store_enabled():
        handler._descartar_corpo()
        return handler._json(403,{'sucesso':False,'erro':'Simulação disponível somente no ambiente local de desenvolvimento.'})
    if not handler._proteger_api():return
    user=handler.sessao
    if user['perfil'] not in rbac.OPERATIONAL:
        handler._descartar_corpo();return handler._json(403,{'sucesso':False,'erro':'Acesso operacional não permitido para este perfil.'})
    if user['perfil']=='diretor_campus' and handler.command!='GET':
        handler._descartar_corpo();return handler._json(403,{'sucesso':False,'erro':'Direção do câmpus: somente consulta.'})
    if admin:
        if not handler._proteger_api() or not handler._exigir_coordenacao():
            return
    try:
        if admin:
            match=re.fullmatch(r'/api/mock-alunos(?:/([1-9][0-9]*))?',path)
            if not match: raise LookupError('Endpoint não encontrado.')
            ident=int(match[1]) if match[1] else None
            if handler.command=='GET':
                data=store.student(ident) if ident else store.students()
            elif handler.command=='POST' and ident is None:
                return handler._json(201,{'sucesso':True,'id':store.save(handler._body())})
            elif handler.command in ('PUT','PATCH') and ident:
                data=store.save(handler._body(),ident)
            elif handler.command=='DELETE' and ident:
                data=store.deactivate(ident)
            else:
                handler._descartar_corpo()
                return handler._json(405,{'sucesso':False,'erro':'Operação não suportada.'})
        elif path=='/simulation-api/alunos' and handler.command=='GET':
            data=[s for s in store.students() if rbac.student_allowed(user,s)]
        elif re.fullmatch(r'/simulation-api/academicos/[1-9][0-9]*',path) and handler.command=='GET':
            data=store.conversation_student(-int(path.rsplit('/',1)[1]))
            if not rbac.student_allowed(user,data):raise LookupError('Aluno não encontrado.')
        else:
            match=re.fullmatch(r'/simulation-api/alunos/(-?[1-9][0-9]*)/conversa',path)
            if not match or handler.command not in ('GET','POST'):
                handler._descartar_corpo()
                raise LookupError('Endpoint não encontrado.')
            aid=int(match[1]);student=store.conversation_student(aid)
            if not rbac.student_allowed(user,student):raise LookupError('Aluno não encontrado.')
            data=store.session(aid,handler._body() if handler.command=='POST' else None)
            if handler.command=='POST':
                import simulation_followup
                try:
                    simulation_followup.sync()
                except sqlite3.Error:
                    # O questionário já foi salvo. A gestão retoma a fila na próxima consulta.
                    data['aviso']='Respostas salvas; o acompanhamento será atualizado na próxima consulta da gestão.'
        return handler._json(200,{'sucesso':True,'dados':data})
    except LookupError as e:
        return handler._json(404,{'sucesso':False,'erro':str(e)})
    except (ValueError,UnicodeDecodeError) as e:
        return handler._json(409 if 'já existente' in str(e) else 400,{'sucesso':False,'erro':str(e)})
    except sqlite3.Error:
        return handler._json(503,{'sucesso':False,'erro':'Falha de persistência local. Tente novamente; a operação não foi confirmada.'})


def store_enabled():
    import os
    return os.environ.get('RADACHE_ENV','development')=='development'
