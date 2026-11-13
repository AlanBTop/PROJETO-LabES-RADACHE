"""Catálogo único de cursos do RADACHE, com nomes equivalentes e IDs estáveis."""
import unicodedata

DEFAULT_CAMPUS = 'Câmpus de Cáceres'
COURSES = (
    'Pedagogia', 'Administração', 'Direito', 'Engenharia Civil',
    'Ciências Biológicas (Licenciatura e Bacharelado)', 'Matemática (Licenciatura)',
    'Medicina', 'Letras (Português e línguas estrangeiras)', 'Ciências Contábeis',
    'Enfermagem', 'Educação Física', 'Química (Licenciatura e Bacharelado)',
    'Física (Licenciatura e Bacharelado)', 'História', 'Geografia',
    'Engenharia Mecânica', 'Agronomia / Engenharia Agronômica', 'Engenharia Elétrica',
    'Ciência da Computação', 'Psicologia', 'Medicina Veterinária', 'Farmácia',
    'Engenharia de Produção', 'Ciências Econômicas (Economia)', 'Sistemas de Informação',
    'Arquitetura e Urbanismo', 'Odontologia', 'Engenharia Química', 'Serviço Social',
    'Administração Pública',
)


def key(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).casefold().split())


ALIASES = {key(name): name for name in COURSES}
for name, variants in (
    (COURSES[4], ('Ciências Biológicas', 'Ciências Biológicas (Licenciatura)', 'Ciências Biológicas (Bacharelado)')),
    (COURSES[5], ('Matemática',)),
    (COURSES[7], ('Letras', 'Letras Português', 'Letras - Português')),
    (COURSES[11], ('Química', 'Química (Licenciatura)', 'Química (Bacharelado)')),
    (COURSES[12], ('Física', 'Física (Licenciatura)', 'Física (Bacharelado)')),
    (COURSES[16], ('Agronomia', 'Engenharia Agronômica')),
    (COURSES[18], ('Ciências da Computação',)),
    (COURSES[23], ('Ciências Econômicas', 'Economia')),
):
    for variant in variants:
        ALIASES[key(variant)] = name


def canonical(value):
    """Não descarta cursos antigos desconhecidos nem altera seus registros."""
    return ALIASES.get(key(value), ' '.join(str(value or '').split()))


def course_id(value):
    name = canonical(value)
    # Preserva referências de nomes curtos já usadas em usuários e chamados.
    stable = {COURSES[4]: 'ciencias-biologicas', COURSES[5]: 'matematica',
              COURSES[7]: 'letras', COURSES[11]: 'quimica', COURSES[12]: 'fisica',
              COURSES[16]: 'agronomia', COURSES[23]: 'ciencias-economicas'}
    return stable.get(name, '-'.join(key(name).split()))


def catalog(extra=()):
    unique = {key(name): name for name in COURSES}
    for value in extra:
        name = canonical(value)
        if name:
            unique.setdefault(key(name), name)
    return [dict(id=course_id(name), nome=name, ativo=True)
            for name in sorted(unique.values(), key=key)]


def available():
    """Inclui nomes legados sem alunos inventados e sem repetir equivalências."""
    from contextlib import closing
    import database
    import simulation_store as store
    extra = [a['curso'] for a in store.students()]
    if database.DB_PATH.exists():
        with closing(database.get_connection()) as conn:
            extra.extend(r[0] for r in conn.execute('SELECT DISTINCT curso FROM alunos'))
    return catalog(extra)
