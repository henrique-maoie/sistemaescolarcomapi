"""
SISTEMA GESTÃO ESCOLAR v2.0 - COMPLETO
Integra Pedagógico, Comercial, Anexos, Auditoria
"""

from flask import Flask, render_template, request, session, redirect, flash, jsonify, send_from_directory
import sqlite3
from datetime import datetime, date, timedelta
import json
import os
import secrets
import unicodedata
from werkzeug.utils import secure_filename
from autenticacao_standalone import Autenticacao
from database import criar_banco_dados

# CONFIG
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'escola.db'))
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'uploads'))
INSTANCE_FOLDER = os.path.join(BASE_DIR, 'instance')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INSTANCE_FOLDER, exist_ok=True)

app = Flask(__name__, instance_path=INSTANCE_FOLDER)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

try:
    criar_banco_dados()
except Exception as erro:
    print(f"Erro ao preparar banco de dados: {erro}")

def get_db():
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    conexao.execute('PRAGMA foreign_keys = ON')
    return conexao

def executar_query(query, params=(), fetch_one=False):
    conexao = None
    try:
        conexao = get_db()
        cursor = conexao.cursor()
        cursor.execute(query, params)
        resultado = cursor.fetchone() if fetch_one else cursor.fetchall()
        return resultado
    except Exception as e:
        print(f"Erro na query: {e}")
        return None
    finally:
        if conexao:
            conexao.close()
            conexao = None

def executar_update(query, params=()):
    conexao = None
    try:
        conexao = get_db()
        cursor = conexao.cursor()
        cursor.execute(query, params)
        conexao.commit()
        return True
    except Exception as e:
        print(f"Erro ao executar: {e}")
        return False
    finally:
        if conexao:
            conexao.close()
            conexao = None

def gerar_matricula(prefixo='ALN'):
    return f"{prefixo}{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

def arquivo_permitido(nome_arquivo):
    return '.' in nome_arquivo and nome_arquivo.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def pode_acessar(*tipos_permitidos):
    tipo = session.get('tipo_usuario')
    return tipo in tipos_permitidos

def normalizar_texto(valor):
    texto = str(valor or '')
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return texto.strip().lower()

def setor_atual():
    return normalizar_texto(session.get('setor_nome') or session.get('cargo') or '')

def usuario_admin():
    return session.get('tipo_usuario') == 'admin'

def usuario_professor():
    return session.get('tipo_usuario') == 'professor'

def funcionario_em_setor(*setores):
    if session.get('tipo_usuario') != 'funcionario':
        return False
    setor = setor_atual()
    cargo = normalizar_texto(session.get('cargo'))
    return any(normalizar_texto(nome) in setor or normalizar_texto(nome) in cargo for nome in setores)

def pode_area_admin():
    return usuario_admin()

def pode_area_pedagogica():
    return usuario_admin() or usuario_professor() or funcionario_em_setor('pedagogico', 'administrativo')

def pode_area_comercial():
    return usuario_admin() or funcionario_em_setor('comercial', 'financeiro')

def pode_ver_alunos():
    return pode_area_pedagogica()

def pode_gerenciar_alunos():
    return usuario_admin() or funcionario_em_setor('pedagogico', 'administrativo')

def pode_ver_relatorios():
    return usuario_admin() or usuario_professor() or funcionario_em_setor('pedagogico', 'administrativo')

def pode_ver_salas():
    return pode_area_pedagogica() or pode_area_comercial()

@app.context_processor
def permissoes_template():
    return {
        'pode_admin': usuario_admin(),
        'pode_pedagogico': pode_area_pedagogica(),
        'pode_comercial': pode_area_comercial(),
        'pode_alunos': pode_ver_alunos(),
        'pode_gerenciar_alunos': pode_gerenciar_alunos(),
        'pode_relatorios': pode_ver_relatorios(),
        'pode_salas': pode_ver_salas(),
    }

def login_requerido():
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'usuario_id' not in session:
                flash('Acesso negado. Faça login primeiro!', 'error')
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def carregar_contexto_usuario(usuario):
    session['nome_usuario'] = usuario.get('email')
    session['cargo'] = ''
    session['setor_nome'] = ''

    tabela = usuario.get('tabela_referencia')
    usuario_id = usuario.get('id_referencia')
    if not tabela or not usuario_id:
        return

    if tabela == 'funcionarios':
        dados = executar_query('''
        SELECT f.nome, f.cargo, COALESCE(s.nome, '') as setor_nome
        FROM funcionarios f
        LEFT JOIN setores s ON f.setor_id = s.id
        WHERE f.id = ?
        ''', (usuario_id,), fetch_one=True)
    elif tabela == 'professores':
        dados = executar_query('SELECT nome, especialidade as cargo FROM professores WHERE id = ?', (usuario_id,), fetch_one=True)
    elif tabela == 'alunos':
        dados = executar_query('SELECT nome FROM alunos WHERE id = ?', (usuario_id,), fetch_one=True)
    else:
        dados = None

    if dados:
        session['nome_usuario'] = dados['nome'] if 'nome' in dados.keys() else usuario.get('email')
        session['cargo'] = dados['cargo'] if 'cargo' in dados.keys() and dados['cargo'] else ''
        session['setor_nome'] = dados['setor_nome'] if 'setor_nome' in dados.keys() and dados['setor_nome'] else ''

def registrar_audit(usuario_id, usuario_tipo, acao, tabela, id_registro, valores_novos):
    executar_update('''
    INSERT INTO audit_log (usuario_id, usuario_tipo, acao, tabela_afetada, id_registro, valores_novos)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (usuario_id, usuario_tipo, acao, tabela, id_registro, json.dumps(valores_novos)))

def consultar_ocupacao_turmas():
    turmas = executar_query('''
    SELECT
        t.id,
        t.codigo,
        t.nome,
        t.nome as turma_nome,
        COALESCE(NULLIF(TRIM(t.sala), ''), 'Sem sala') as sala_nome,
        COALESCE(t.capacidade, 0) as capacidade,
        c.nome as curso_nome,
        p.nome as professor_nome,
        COUNT(m.id) as ocupadas,
        CASE
            WHEN COALESCE(t.capacidade, 0) - COUNT(m.id) > 0
            THEN COALESCE(t.capacidade, 0) - COUNT(m.id)
            ELSE 0
        END as vagas_disponiveis
    FROM turmas t
    JOIN cursos c ON t.curso_id = c.id
    JOIN professores p ON t.professor_id = p.id
    LEFT JOIN matriculas m ON t.id = m.turma_id AND m.status = 'ativa'
    WHERE t.ativa = 1
    GROUP BY t.id
    ORDER BY c.nome, t.nome
    ''') or []
    return [dict(turma) for turma in turmas]

# ============================================================================
# AUTENTICAÇÃO
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        usuario = Autenticacao.autenticar(email, senha)

        if usuario:
            session['usuario_id'] = usuario['id_referencia']
            session['email'] = usuario['email']
            session['tipo_usuario'] = usuario['tipo_usuario']
            session['tabela_referencia'] = usuario['tabela_referencia']
            carregar_contexto_usuario(usuario)
            registrar_audit(usuario['id_referencia'], usuario['tipo_usuario'], 'LOGIN', 'usuarios', usuario['id_referencia'], {})
            flash('Login realizado!', 'success')
            return redirect('/dashboard')
        else:
            flash('Email ou senha incorretos!', 'error')

    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        cpf = (request.form.get('cpf') or '').strip()
        senha = request.form.get('senha') or ''
        telefone = (request.form.get('telefone') or '').strip()
        data_nascimento = request.form.get('data_nascimento')
        conexao = None

        if not nome or not email or not cpf or not senha:
            flash('Preencha todos os campos obrigatorios.', 'error')
            return render_template('cadastro.html')

        try:
            conexao = get_db()
            cursor = conexao.cursor()
            senha_hash = Autenticacao.hash_senha(senha)

            cursor.execute('''
            INSERT INTO alunos (nome, email, cpf, senha, matricula, data_nascimento, telefone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (nome, email, cpf, senha_hash, gerar_matricula(), data_nascimento, telefone))

            aluno_id = cursor.lastrowid

            cursor.execute('''
            INSERT INTO usuarios (email, senha, tipo_usuario, tabela_referencia, id_referencia)
            VALUES (?, ?, ?, ?, ?)
            ''', (email, senha_hash, 'aluno', 'alunos', aluno_id))

            cursor.execute('''
            INSERT INTO status_aluno (aluno_id, status, data_atualizacao)
            VALUES (?, ?, ?)
            ''', (aluno_id, 'Nao Iniciou', date.today()))

            conexao.commit()
            conexao.close()

            flash('Cadastro realizado! Faça login.', 'success')
            return redirect('/login')
        except sqlite3.IntegrityError:
            if conexao:
                conexao.rollback()
            flash('Email ou CPF ja cadastrado.', 'error')
        except Exception as e:
            if conexao:
                conexao.rollback()
            flash(f'Erro: {str(e)}', 'error')
        finally:
            if conexao:
                conexao.close()

    return render_template('cadastro.html')

@app.route('/logout')
def logout():
    registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'LOGOUT', 'usuarios', session.get('usuario_id'), {})
    session.clear()
    flash('Desconectado!', 'info')
    return redirect('/login')

@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect('/dashboard')
    return redirect('/login')

# ============================================================================
# DASHBOARD v2 - NOVO COM GRÁFICOS
# ============================================================================

@app.route('/dashboard')
@login_requerido()
def dashboard():
    tipo_usuario = session.get('tipo_usuario')
    usuario_id = session.get('usuario_id')

    if pode_area_comercial() and not usuario_admin() and not pode_area_pedagogica():
        return redirect('/comercial')

    # Estatísticas gerais
    total_alunos = executar_query('SELECT COUNT(*) FROM alunos WHERE ativo = 1', fetch_one=True)[0] or 0
    total_professores = executar_query('SELECT COUNT(*) FROM professores WHERE ativo = 1', fetch_one=True)[0] or 0
    total_turmas = executar_query('SELECT COUNT(*) FROM turmas WHERE ativa = 1', fetch_one=True)[0] or 0
    total_cursos = executar_query('SELECT COUNT(*) FROM cursos WHERE ativo = 1', fetch_one=True)[0] or 0

    # Dados para gráficos
    alunos_por_status = executar_query('''
    SELECT COALESCE(status, 'Não informado') as status, COUNT(*) as total
    FROM status_aluno GROUP BY status
    ''') or []

    receita_mes = executar_query('''
    SELECT SUM(valor_pago) FROM financeiro WHERE strftime('%Y-%m', data_vencimento) = strftime('%Y-%m', 'now')
    ''', fetch_one=True)[0] or 0

    matriculas_mes = executar_query('''
    SELECT COUNT(*) FROM matriculas WHERE strftime('%Y-%m', data_matricula) = strftime('%Y-%m', 'now')
    ''', fetch_one=True)[0] or 0

    dados = {
        'tipo_usuario': tipo_usuario,
        'usuario_id': usuario_id,
        'total_alunos': total_alunos,
        'total_professores': total_professores,
        'total_turmas': total_turmas,
        'total_cursos': total_cursos,
        'receita_mes': float(receita_mes) if receita_mes else 0,
        'matriculas_mes': matriculas_mes,
        'alunos_por_status': [dict(s) for s in alunos_por_status] if alunos_por_status else []
    }

    # Dados por tipo de usuário
    if tipo_usuario == 'aluno':
        aluno = executar_query('SELECT * FROM alunos WHERE id = ?', (usuario_id,), fetch_one=True)
        turmas = executar_query('''
        SELECT t.*, p.nome as professor_nome, c.nome as curso_nome
        FROM turmas t
        JOIN matriculas m ON t.id = m.turma_id
        JOIN professores p ON t.professor_id = p.id
        JOIN cursos c ON t.curso_id = c.id
        WHERE m.aluno_id = ?
        ''', (usuario_id,))
        dados.update({
            'aluno': dict(aluno) if aluno else {},
            'turmas': [dict(t) for t in turmas] if turmas else []
        })

    elif tipo_usuario == 'professor':
        turmas = executar_query('''
        SELECT t.*, c.nome as curso_nome, COUNT(m.id) as total_alunos
        FROM turmas t
        JOIN cursos c ON t.curso_id = c.id
        LEFT JOIN matriculas m ON t.id = m.turma_id
        WHERE t.professor_id = ?
        GROUP BY t.id
        ''', (usuario_id,))
        dados['turmas'] = [dict(t) for t in turmas] if turmas else []

    return render_template('dashboard_v2.html', **dados)

# ============================================================================
# TURMAS
# ============================================================================

@app.route('/turmas')
@login_requerido()
def listar_turmas():
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    turmas = executar_query('''
    SELECT t.*, c.nome as curso_nome, p.nome as professor_nome, COUNT(m.id) as total_alunos
    FROM turmas t
    JOIN cursos c ON t.curso_id = c.id
    JOIN professores p ON t.professor_id = p.id
    LEFT JOIN matriculas m ON t.id = m.turma_id
    GROUP BY t.id ORDER BY t.data_inicio DESC
    ''')

    return render_template('turmas/listar.html', turmas=[dict(t) for t in turmas] if turmas else [])

@app.route('/turma/nova', methods=['GET', 'POST'])
@login_requerido()
def nova_turma():
    if not usuario_admin():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        if executar_update('''
        INSERT INTO turmas (codigo, nome, curso_id, professor_id, data_inicio, data_fim, horario, sala, capacidade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (request.form.get('codigo'), request.form.get('nome'), request.form.get('curso_id'),
              request.form.get('professor_id'), request.form.get('data_inicio'), request.form.get('data_fim'),
              request.form.get('horario'), request.form.get('sala'), request.form.get('capacidade'))):
            flash('Turma criada!', 'success')
            registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'CRIAR_TURMA', 'turmas', 1, {})
            return redirect('/turmas')
        flash('Erro!', 'error')

    cursos = executar_query('SELECT * FROM cursos WHERE ativo = 1')
    professores = executar_query('SELECT * FROM professores WHERE ativo = 1')
    return render_template('turmas/nova.html',
                         cursos=[dict(c) for c in cursos] if cursos else [],
                         professores=[dict(p) for p in professores] if professores else [])

# ============================================================================
# ALUNOS
# ============================================================================

@app.route('/alunos')
@login_requerido()
def listar_alunos():
    if not pode_ver_alunos():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    alunos = executar_query('SELECT * FROM alunos WHERE ativo = 1 ORDER BY nome')
    return render_template('alunos/listar.html', alunos=[dict(a) for a in alunos] if alunos else [])

@app.route('/aluno/novo', methods=['GET', 'POST'])
@login_requerido()
def novo_aluno():
    if not (usuario_admin() or funcionario_em_setor('pedagogico', 'administrativo')):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        conexao = None
        try:
            conexao = get_db()
            cursor = conexao.cursor()
            senha = request.form.get('senha') or ''
            senha_hash = Autenticacao.hash_senha(senha)

            cursor.execute('''
            INSERT INTO alunos (nome, email, cpf, senha, matricula, data_nascimento, telefone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (request.form.get('nome'), request.form.get('email'), request.form.get('cpf'),
                  senha_hash,
                  gerar_matricula(), request.form.get('data_nascimento'),
                  request.form.get('telefone')))

            aluno_id = cursor.lastrowid

            cursor.execute('''
            INSERT INTO usuarios (email, senha, tipo_usuario, tabela_referencia, id_referencia)
            VALUES (?, ?, ?, ?, ?)
            ''', (request.form.get('email'), senha_hash,
                  'aluno', 'alunos', aluno_id))

            # Criar status inicial
            cursor.execute('''
            INSERT INTO status_aluno (aluno_id, status, data_atualizacao)
            VALUES (?, ?, ?)
            ''', (aluno_id, 'Não Iniciou', date.today()))

            conexao.commit()
            conexao.close()
            conexao = None
            flash('Aluno criado!', 'success')
            registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'CRIAR_ALUNO', 'alunos', aluno_id, {})
            return redirect('/alunos')
        except sqlite3.IntegrityError:
            if conexao:
                conexao.rollback()
            flash('Email, CPF ou matricula ja cadastrado.', 'error')
        except Exception as e:
            if conexao:
                conexao.rollback()
            flash(f'Erro: {str(e)}', 'error')
        finally:
            if conexao:
                conexao.close()

    return render_template('alunos/novo.html')

@app.route('/aluno/<int:aluno_id>')
@login_requerido()
def detalhe_aluno(aluno_id):
    if session.get('tipo_usuario') == 'aluno' and session.get('usuario_id') != aluno_id:
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')
    if session.get('tipo_usuario') != 'aluno' and not pode_ver_alunos():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    aluno = executar_query('SELECT * FROM alunos WHERE id = ?', (aluno_id,), fetch_one=True)
    if not aluno:
        flash('Aluno não encontrado!', 'error')
        return redirect('/alunos')

    turmas = executar_query('''
    SELECT t.*, c.nome as curso_nome, p.nome as professor_nome
    FROM turmas t
    JOIN matriculas m ON t.id = m.turma_id
    JOIN cursos c ON t.curso_id = c.id
    JOIN professores p ON t.professor_id = p.id
    WHERE m.aluno_id = ?
    ''', (aluno_id,))

    notas = executar_query('''
    SELECT n.*, m.nome as modulo_nome
    FROM notas n
    JOIN matriculas mat ON n.matricula_id = mat.id
    JOIN modulos m ON n.modulo_id = m.id
    WHERE mat.aluno_id = ?
    ''', (aluno_id,))

    frequencia = executar_query('''
    SELECT COUNT(*) as total, SUM(CASE WHEN presente = 1 THEN 1 ELSE 0 END) as presentes
    FROM frequencias f
    JOIN matriculas m ON f.matricula_id = m.id
    WHERE m.aluno_id = ?
    ''', (aluno_id,), fetch_one=True)

    status = executar_query('''
    SELECT * FROM status_aluno WHERE aluno_id = ? ORDER BY data_criacao DESC LIMIT 1
    ''', (aluno_id,), fetch_one=True)

    relatorios = executar_query('''
    SELECT * FROM relatorios_aluno WHERE aluno_id = ? ORDER BY data_criacao DESC
    ''', (aluno_id,))

    return render_template('alunos/detalhe.html',
                         aluno=dict(aluno),
                         turmas=[dict(t) for t in turmas] if turmas else [],
                         notas=[dict(n) for n in notas] if notas else [],
                         frequencia=dict(frequencia) if frequencia else {},
                         status=dict(status) if status else {},
                         relatorios=[dict(r) for r in relatorios] if relatorios else [])

# ============================================================================
# PEDAGOGICO - NOVO
# ============================================================================

@app.route('/pedagogico')
@login_requerido()
def pedagogico():
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    turmas = executar_query('''
    SELECT t.*, p.nome as professor_nome, c.nome as curso_nome, COUNT(m.id) as total_alunos
    FROM turmas t
    JOIN professores p ON t.professor_id = p.id
    JOIN cursos c ON t.curso_id = c.id
    LEFT JOIN matriculas m ON t.id = m.turma_id
    GROUP BY t.id
    ORDER BY t.data_inicio DESC
    ''')

    return render_template('pedagogico/dashboard.html',
                         turmas=[dict(t) for t in turmas] if turmas else [])

@app.route('/pedagogico/turmas')
@login_requerido()
def pedagogico_turmas():
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    turmas = executar_query('''
    SELECT t.*, p.nome as professor_nome, c.nome as curso_nome, COUNT(m.id) as total_alunos
    FROM turmas t
    JOIN professores p ON t.professor_id = p.id
    JOIN cursos c ON t.curso_id = c.id
    LEFT JOIN matriculas m ON t.id = m.turma_id AND m.status = 'ativa'
    GROUP BY t.id
    ORDER BY t.data_inicio DESC
    ''')

    return render_template('pedagogico/turmas.html',
                         turmas=[dict(t) for t in turmas] if turmas else [])

@app.route('/pedagogico/salas')
@login_requerido()
def pedagogico_salas():
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    return render_template('pedagogico/salas.html', salas=consultar_ocupacao_turmas())

@app.route('/pedagogico/turma/<int:turma_id>/alunos')
@login_requerido()
def pedagogico_turma_alunos(turma_id):
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    turma = executar_query('''
    SELECT t.*, c.nome as curso_nome
    FROM turmas t
    JOIN cursos c ON t.curso_id = c.id
    WHERE t.id = ?
    ''', (turma_id,), fetch_one=True)
    if not turma:
        flash('Turma nao encontrada!', 'error')
        return redirect('/pedagogico')

    alunos = executar_query('''
    SELECT a.*, m.status as status_matricula, m.data_matricula
    FROM matriculas m
    JOIN alunos a ON m.aluno_id = a.id
    WHERE m.turma_id = ?
    ORDER BY a.nome
    ''', (turma_id,))

    return render_template('pedagogico/turma_alunos.html',
                         turma=dict(turma),
                         alunos=[dict(a) for a in alunos] if alunos else [])

@app.route('/pedagogico/aluno/<int:aluno_id>')
@login_requerido()
def pedagogico_aluno_detalhes(aluno_id):
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    aluno = executar_query('SELECT * FROM alunos WHERE id = ?', (aluno_id,), fetch_one=True)
    if not aluno:
        flash('Aluno não encontrado!', 'error')
        return redirect('/pedagogico')

    status = executar_query('''
    SELECT * FROM status_aluno WHERE aluno_id = ? ORDER BY data_criacao DESC LIMIT 1
    ''', (aluno_id,), fetch_one=True)

    turmas = executar_query('''
    SELECT t.*, c.nome as curso_nome, p.nome as professor_nome
    FROM turmas t
    JOIN matriculas m ON t.id = m.turma_id
    JOIN cursos c ON t.curso_id = c.id
    JOIN professores p ON t.professor_id = p.id
    WHERE m.aluno_id = ?
    ''', (aluno_id,))

    notas = executar_query('''
    SELECT n.*, m.nome as modulo_nome, t.nome as turma_nome
    FROM notas n
    JOIN matriculas mat ON n.matricula_id = mat.id
    JOIN modulos m ON n.modulo_id = m.id
    JOIN turmas t ON mat.turma_id = t.id
    WHERE mat.aluno_id = ?
    ORDER BY t.nome
    ''', (aluno_id,))

    frequencia = executar_query('''
    SELECT COUNT(*) as total, SUM(CASE WHEN presente = 1 THEN 1 ELSE 0 END) as presentes
    FROM frequencias f
    JOIN matriculas m ON f.matricula_id = m.id
    WHERE m.aluno_id = ?
    ''', (aluno_id,), fetch_one=True)

    relatorios = executar_query('''
    SELECT * FROM relatorios_aluno WHERE aluno_id = ? ORDER BY data_criacao DESC
    ''', (aluno_id,))

    return render_template('pedagogico/aluno_detalhes.html',
                         aluno=dict(aluno),
                         status=dict(status) if status else {},
                         turmas=[dict(t) for t in turmas] if turmas else [],
                         notas=[dict(n) for n in notas] if notas else [],
                         frequencia=dict(frequencia) if frequencia else {},
                         relatorios=[dict(r) for r in relatorios] if relatorios else [])

@app.route('/pedagogico/aluno/<int:aluno_id>/relatorio/novo', methods=['POST'])
@login_requerido()
def novo_relatorio_aluno(aluno_id):
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/pedagogico')

    titulo = request.form.get('titulo')
    conteudo = request.form.get('conteudo')

    executar_update('''
    INSERT INTO relatorios_aluno (aluno_id, tipo, titulo, conteudo, criado_por)
    VALUES (?, ?, ?, ?, ?)
    ''', (aluno_id, 'pedagogico', titulo, conteudo, session.get('usuario_id')))

    registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'CRIAR_RELATORIO', 'relatorios_aluno', aluno_id, {'titulo': titulo})
    flash('Relatório criado!', 'success')
    return redirect(f'/pedagogico/aluno/{aluno_id}')

@app.route('/pedagogico/aluno/<int:aluno_id>/status/novo', methods=['POST'])
@login_requerido()
def novo_status_aluno(aluno_id):
    if not (usuario_admin() or funcionario_em_setor('pedagogico', 'administrativo')):
        flash('Acesso negado!', 'error')
        return redirect('/pedagogico')

    status = request.form.get('status')
    motivo = request.form.get('motivo')

    executar_update('''
    INSERT INTO status_aluno (aluno_id, status, motivo, data_atualizacao)
    VALUES (?, ?, ?, ?)
    ''', (aluno_id, status, motivo, date.today()))

    registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'ALTERAR_STATUS', 'status_aluno', aluno_id, {'status': status})
    flash(f'Status alterado para: {status}', 'success')
    return redirect(f'/pedagogico/aluno/{aluno_id}')

# ============================================================================
# COMERCIAL - NOVO
# ============================================================================

@app.route('/comercial')
@login_requerido()
def comercial():
    if not pode_area_comercial():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    matriculas_mes = executar_query('''
    SELECT COUNT(*) FROM matriculas WHERE strftime('%Y-%m', data_matricula) = strftime('%Y-%m', 'now')
    ''', fetch_one=True)[0] or 0

    receita_mes = executar_query('''
    SELECT SUM(valor_pago) FROM financeiro WHERE strftime('%Y-%m', data_vencimento) = strftime('%Y-%m', 'now')
    ''', fetch_one=True)[0] or 0

    pendente = executar_query('''
    SELECT SUM(valor_total - valor_pago) FROM financeiro WHERE status = 'pendente'
    ''', fetch_one=True)[0] or 0

    turmas_vagas = consultar_ocupacao_turmas()
    total_vagas = sum(t['capacidade'] or 0 for t in turmas_vagas)
    vagas_ocupadas = sum(t['ocupadas'] or 0 for t in turmas_vagas)
    vagas_disponiveis = sum(t['vagas_disponiveis'] or 0 for t in turmas_vagas)

    return render_template('comercial/dashboard.html',
                         matriculas_mes=matriculas_mes,
                         receita_mes=float(receita_mes) if receita_mes else 0,
                         pendente=float(pendente) if pendente else 0,
                         total_vagas=total_vagas,
                         vagas_ocupadas=vagas_ocupadas,
                         vagas_disponiveis=vagas_disponiveis,
                         turmas_vagas=turmas_vagas[:6])

@app.route('/comercial/vagas')
@login_requerido()
def comercial_vagas():
    if not pode_area_comercial():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    return render_template('comercial/vagas.html', turmas=consultar_ocupacao_turmas())

def salvar_matricula_comercial():
    conexao = None
    try:
        aluno_id = request.form.get('aluno_id')
        turma_id = request.form.get('turma_id')
        valor_total = float(request.form.get('valor_total') or 0)
        parcelas = int(request.form.get('parcelas') or 0)

        if valor_total <= 0 or parcelas <= 0:
            flash('Informe valor total e quantidade de parcelas validos.', 'error')
            return redirect('/comercial/matricula/nova')

        conexao = get_db()
        cursor = conexao.cursor()

        cursor.execute('''
        SELECT COALESCE(t.capacidade, 0) as capacidade, COUNT(m.id) as ocupadas
        FROM turmas t
        LEFT JOIN matriculas m ON t.id = m.turma_id AND m.status = 'ativa'
        WHERE t.id = ? AND t.ativa = 1
        GROUP BY t.id
        ''', (turma_id,))
        ocupacao = cursor.fetchone()
        if not ocupacao or ocupacao['capacidade'] <= ocupacao['ocupadas']:
            flash('Esta turma nao possui vagas disponiveis.', 'error')
            return redirect('/comercial/matricula/nova')

        cursor.execute('''
        INSERT INTO matriculas (aluno_id, turma_id, data_matricula, status)
        VALUES (?, ?, ?, ?)
        ''', (aluno_id, turma_id, date.today(), 'ativa'))
        matricula_id = cursor.lastrowid

        cursor.execute('''
        INSERT INTO financeiro (matricula_id, valor_total, data_vencimento, status, parcelas, descricao)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (matricula_id, valor_total, date.today() + timedelta(days=30), 'pendente', parcelas, 'Matricula'))
        financeiro_id = cursor.lastrowid

        valor_parcela = round(valor_total / parcelas, 2)
        for i in range(parcelas):
            data_vencimento = date.today() + timedelta(days=30 * (i + 1))
            cursor.execute('''
            INSERT INTO parcelas (financeiro_id, numero_parcela, valor_parcela, data_vencimento, status)
            VALUES (?, ?, ?, ?, ?)
            ''', (financeiro_id, i + 1, valor_parcela, data_vencimento, 'pendente'))

        conexao.commit()
        conexao.close()
        conexao = None

        registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'NOVA_MATRICULA', 'matriculas', matricula_id, {})
        flash('Matricula criada!', 'success')
        return redirect('/comercial/matriculas')
    except sqlite3.IntegrityError:
        if conexao:
            conexao.rollback()
        flash('Este aluno ja esta matriculado nessa turma.', 'error')
    except ValueError:
        if conexao:
            conexao.rollback()
        flash('Valor total ou quantidade de parcelas invalida.', 'error')
    except Exception as e:
        if conexao:
            conexao.rollback()
        flash(f'Erro: {str(e)}', 'error')
    finally:
        if conexao:
            conexao.close()

    return redirect('/comercial/matricula/nova')

@app.route('/comercial/matricula/nova', methods=['GET', 'POST'])
@login_requerido()
def nova_matricula_comercial():
    if not pode_area_comercial():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        return salvar_matricula_comercial()
        aluno_id = request.form.get('aluno_id')
        turma_id = request.form.get('turma_id')
        valor_total = float(request.form.get('valor_total'))
        parcelas = int(request.form.get('parcelas'))

        # Criar matrícula
        executar_update('''
        INSERT INTO matriculas (aluno_id, turma_id, data_matricula, status)
        VALUES (?, ?, ?, ?)
        ''', (aluno_id, turma_id, date.today(), 'ativa'))

        matricula_id = executar_query('SELECT last_insert_rowid()', fetch_one=True)[0]

        # Criar financeiro
        executar_update('''
        INSERT INTO financeiro (matricula_id, valor_total, data_vencimento, status, parcelas, descricao)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (matricula_id, valor_total, date.today() + timedelta(days=30), 'pendente', parcelas, 'Matrícula'))

        # Criar parcelas
        valor_parcela = valor_total / parcelas
        for i in range(parcelas):
            data_vencimento = date.today() + timedelta(days=30 * (i + 1))
            executar_update('''
            INSERT INTO parcelas (financeiro_id, numero_parcela, valor_parcela, data_vencimento, status)
            VALUES (?, ?, ?, ?, ?)
            ''', (matricula_id, i + 1, valor_parcela, data_vencimento, 'pendente'))

        registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'NOVA_MATRICULA', 'matriculas', matricula_id, {})
        flash('Matrícula criada!', 'success')
        return redirect('/comercial/matriculas')

    alunos = executar_query('SELECT id, nome FROM alunos WHERE ativo = 1 ORDER BY nome')
    turmas = [turma for turma in consultar_ocupacao_turmas() if turma['vagas_disponiveis'] > 0]
    cursos = executar_query('SELECT id, nome, valor FROM cursos WHERE ativo = 1')

    return render_template('comercial/matricula_nova.html',
                         alunos=[dict(a) for a in alunos] if alunos else [],
                         turmas=[dict(t) for t in turmas] if turmas else [],
                         cursos=[dict(c) for c in cursos] if cursos else [])

@app.route('/comercial/matriculas')
@login_requerido()
def listar_matriculas_comercial():
    if not pode_area_comercial():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    matriculas = executar_query('''
    SELECT m.*, a.nome as aluno_nome, t.nome as turma_nome, f.id as financeiro_id
    FROM matriculas m
    JOIN alunos a ON m.aluno_id = a.id
    JOIN turmas t ON m.turma_id = t.id
    LEFT JOIN financeiro f ON f.matricula_id = m.id
    ORDER BY m.data_matricula DESC
    ''')

    return render_template('comercial/matriculas.html',
                         matriculas=[dict(m) for m in matriculas] if matriculas else [])

@app.route('/comercial/financeiro')
@login_requerido()
def comercial_financeiro():
    if not pode_area_comercial():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    financeiros = executar_query('''
    SELECT f.*, a.nome as aluno_nome, t.nome as turma_nome
    FROM financeiro f
    JOIN matriculas m ON f.matricula_id = m.id
    JOIN alunos a ON m.aluno_id = a.id
    JOIN turmas t ON m.turma_id = t.id
    ORDER BY f.data_vencimento
    ''')

    return render_template('comercial/financeiro.html',
                         financeiros=[dict(f) for f in financeiros] if financeiros else [])

@app.route('/comercial/parcelas/<int:financeiro_id>')
@login_requerido()
def ver_parcelas(financeiro_id):
    if not pode_area_comercial():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    financeiro = executar_query('SELECT * FROM financeiro WHERE id = ?', (financeiro_id,), fetch_one=True)
    if not financeiro:
        flash('Não encontrado!', 'error')
        return redirect('/comercial/financeiro')

    parcelas = executar_query('''
    SELECT * FROM parcelas WHERE financeiro_id = ? ORDER BY numero_parcela
    ''', (financeiro_id,))

    return render_template('comercial/parcelas.html',
                         financeiro=dict(financeiro),
                         parcelas=[dict(p) for p in parcelas] if parcelas else [])

@app.route('/comercial/parcela/<int:parcela_id>/pagar', methods=['POST'])
@login_requerido()
def pagar_parcela(parcela_id):
    if not pode_area_comercial():
        flash('Acesso negado!', 'error')
        return redirect('/comercial/financeiro')

    metodo = request.form.get('metodo_pagamento', 'dinheiro')
    conexao = None

    try:
        conexao = get_db()
        cursor = conexao.cursor()
        cursor.execute('SELECT * FROM parcelas WHERE id = ?', (parcela_id,))
        parcela = cursor.fetchone()

        if not parcela:
            flash('Parcela nao encontrada.', 'error')
            return redirect('/comercial/financeiro')

        cursor.execute('''
        UPDATE parcelas
        SET status = 'pago', data_pagamento = ?, metodo_pagamento = ?
        WHERE id = ?
        ''', (date.today(), metodo, parcela_id))

        financeiro_id = parcela['financeiro_id']
        cursor.execute('''
        SELECT COALESCE(SUM(valor_parcela), 0)
        FROM parcelas
        WHERE financeiro_id = ? AND status = 'pago'
        ''', (financeiro_id,))
        valor_pago = cursor.fetchone()[0] or 0

        cursor.execute('SELECT valor_total FROM financeiro WHERE id = ?', (financeiro_id,))
        financeiro = cursor.fetchone()
        status_financeiro = 'pago' if financeiro and valor_pago >= (financeiro['valor_total'] or 0) else 'pendente'

        cursor.execute('''
        UPDATE financeiro
        SET valor_pago = ?, status = ?
        WHERE id = ?
        ''', (valor_pago, status_financeiro, financeiro_id))

        conexao.commit()
        conexao.close()
        conexao = None

        registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'PAGAR_PARCELA', 'parcelas', parcela_id, {})
        flash('Pagamento registrado!', 'success')
    except Exception as e:
        if conexao:
            conexao.rollback()
        flash(f'Erro ao registrar pagamento: {str(e)}', 'error')
    finally:
        if conexao:
            conexao.close()

    return redirect(request.referrer or '/comercial/financeiro')

# ============================================================================
# ANEXOS
# ============================================================================

@app.route('/aluno/<int:aluno_id>/anexos')
@login_requerido()
def anexos_aluno(aluno_id):
    if session.get('tipo_usuario') == 'aluno' and session.get('usuario_id') != aluno_id:
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')
    if session.get('tipo_usuario') != 'aluno' and not pode_ver_alunos():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    aluno = executar_query('SELECT * FROM alunos WHERE id = ?', (aluno_id,), fetch_one=True)
    if not aluno:
        flash('Aluno não encontrado!', 'error')
        return redirect('/alunos')

    anexos = executar_query('''
    SELECT * FROM anexos WHERE aluno_id = ? ORDER BY data_upload DESC
    ''', (aluno_id,))

    return render_template('alunos/anexos.html',
                         aluno=dict(aluno),
                         anexos=[dict(a) for a in anexos] if anexos else [])

def salvar_anexo_aluno(aluno_id):
    if not (usuario_admin() or funcionario_em_setor('pedagogico', 'administrativo')):
        flash('Acesso negado!', 'error')
        return redirect(f'/aluno/{aluno_id}/anexos')

    aluno = executar_query('SELECT id FROM alunos WHERE id = ?', (aluno_id,), fetch_one=True)
    if not aluno:
        flash('Aluno nao encontrado!', 'error')
        return redirect('/alunos')

    if 'arquivo' not in request.files:
        flash('Nenhum arquivo selecionado!', 'error')
        return redirect(f'/aluno/{aluno_id}/anexos')

    arquivo = request.files['arquivo']
    if not arquivo.filename:
        flash('Nenhum arquivo selecionado!', 'error')
        return redirect(f'/aluno/{aluno_id}/anexos')

    nome_original = secure_filename(arquivo.filename)
    if not nome_original or not arquivo_permitido(nome_original):
        flash('Tipo de arquivo nao permitido.', 'error')
        return redirect(f'/aluno/{aluno_id}/anexos')

    nome_arquivo = f"{aluno_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{nome_original}"
    caminho_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)
    arquivo.save(caminho_arquivo)
    tamanho = os.path.getsize(caminho_arquivo)

    tipo = request.form.get('tipo', 'documento')
    titulo = request.form.get('titulo') or arquivo.filename

    executar_update('''
    INSERT INTO anexos (aluno_id, tipo, titulo, arquivo, arquivo_nome, arquivo_tamanho, arquivo_tipo)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (aluno_id, tipo, titulo, nome_arquivo, arquivo.filename, tamanho, arquivo.content_type))

    registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'UPLOAD_ANEXO', 'anexos', aluno_id, {'tipo': tipo})
    flash('Anexo enviado!', 'success')
    return redirect(f'/aluno/{aluno_id}/anexos')

@app.route('/anexo/<int:anexo_id>/download')
@login_requerido()
def baixar_anexo(anexo_id):
    anexo = executar_query('SELECT * FROM anexos WHERE id = ?', (anexo_id,), fetch_one=True)
    if not anexo:
        flash('Anexo nao encontrado.', 'error')
        return redirect('/dashboard')

    if session.get('tipo_usuario') == 'aluno' and session.get('usuario_id') != anexo['aluno_id']:
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')
    if session.get('tipo_usuario') != 'aluno' and not pode_ver_alunos():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    nome_arquivo = os.path.basename(anexo['arquivo'])
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        nome_arquivo,
        as_attachment=True,
        download_name=anexo['arquivo_nome']
    )

@app.route('/aluno/<int:aluno_id>/anexo/novo', methods=['POST'])
@login_requerido()
def novo_anexo(aluno_id):
    return salvar_anexo_aluno(aluno_id)
    if not (usuario_admin() or funcionario_em_setor('pedagogico', 'administrativo')):
        flash('Acesso negado!', 'error')
        return redirect(f'/aluno/{aluno_id}/anexos')

    if 'arquivo' not in request.files:
        flash('Nenhum arquivo selecionado!', 'error')
        return redirect(f'/aluno/{aluno_id}/anexos')

    arquivo = request.files['arquivo']
    if arquivo.filename == '':
        flash('Nenhum arquivo selecionado!', 'error')
        return redirect(f'/aluno/{aluno_id}/anexos')

    nome_arquivo = f"{aluno_id}_{datetime.now().timestamp()}_{arquivo.filename}"
    caminho_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)
    arquivo.save(caminho_arquivo)

    tipo = request.form.get('tipo', 'documento')
    titulo = request.form.get('titulo', arquivo.filename)

    executar_update('''
    INSERT INTO anexos (aluno_id, tipo, titulo, arquivo, arquivo_nome, arquivo_tamanho, arquivo_tipo)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (aluno_id, tipo, titulo, caminho_arquivo, arquivo.filename, len(arquivo.getvalue()), arquivo.content_type))

    registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'UPLOAD_ANEXO', 'anexos', aluno_id, {'tipo': tipo})
    flash('Anexo enviado!', 'success')
    return redirect(f'/aluno/{aluno_id}/anexos')

# ============================================================================
# FREQUÊNCIA E NOTAS
# ============================================================================

@app.route('/turma/<int:turma_id>/frequencia', methods=['GET', 'POST'])
@login_requerido()
def frequencia_turma(turma_id):
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    turma = executar_query('SELECT * FROM turmas WHERE id = ?', (turma_id,), fetch_one=True)
    if not turma:
        flash('Turma não encontrada!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        data_aula = request.form.get('data_aula')
        matriculas = executar_query('''
        SELECT m.id FROM matriculas m WHERE m.turma_id = ?
        ''', (turma_id,))

        for matricula in matriculas or []:
            presente = request.form.get(f'presente_{matricula["id"]}')
            registro = executar_query('''
            SELECT id FROM frequencias WHERE matricula_id = ? AND data_aula = ?
            ''', (matricula['id'], data_aula), fetch_one=True)

            if registro:
                executar_update('''
                UPDATE frequencias SET presente = ? WHERE id = ?
                ''', (1 if presente else 0, registro['id']))
            else:
                executar_update('''
                INSERT INTO frequencias (matricula_id, data_aula, presente)
                VALUES (?, ?, ?)
                ''', (matricula['id'], data_aula, 1 if presente else 0))

        registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'REGISTRAR_FREQUENCIA', 'frequencias', turma_id, {})
        flash('Frequência registrada!', 'success')
        return redirect(f'/turma/{turma_id}/frequencia')

    alunos = executar_query('''
    SELECT m.id, a.id as aluno_id, a.nome
    FROM matriculas m
    JOIN alunos a ON m.aluno_id = a.id
    WHERE m.turma_id = ?
    ''', (turma_id,))

    return render_template('frequencia/registrar.html',
                         turma=dict(turma),
                         alunos=[dict(a) for a in alunos] if alunos else [])

@app.route('/turma/<int:turma_id>/notas', methods=['GET', 'POST'])
@login_requerido()
def notas_turma(turma_id):
    if not pode_area_pedagogica():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    turma = executar_query('SELECT * FROM turmas WHERE id = ?', (turma_id,), fetch_one=True)
    if not turma:
        flash('Turma não encontrada!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        matricula_id = request.form.get('matricula_id')
        modulo_id = request.form.get('modulo_id')
        primeira_nota = float(request.form.get('primeira_nota', 0))
        segunda_nota = float(request.form.get('segunda_nota', 0))
        terceira_nota = float(request.form.get('terceira_nota', 0))
        media = (primeira_nota + segunda_nota + terceira_nota) / 3

        nota_existente = executar_query('''
        SELECT id FROM notas WHERE matricula_id = ? AND modulo_id = ?
        ''', (matricula_id, modulo_id), fetch_one=True)

        if nota_existente:
            executar_update('''
            UPDATE notas
            SET primeira_nota = ?, segunda_nota = ?, terceira_nota = ?, media_final = ?
            WHERE id = ?
            ''', (primeira_nota, segunda_nota, terceira_nota, media, nota_existente['id']))
        else:
            executar_update('''
            INSERT INTO notas (matricula_id, modulo_id, primeira_nota, segunda_nota, terceira_nota, media_final)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (matricula_id, modulo_id, primeira_nota, segunda_nota, terceira_nota, media))

        registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'REGISTRAR_NOTAS', 'notas', matricula_id, {})
        flash('Notas registradas!', 'success')

    modulos = executar_query('''
    SELECT * FROM modulos WHERE curso_id = (SELECT curso_id FROM turmas WHERE id = ?)
    ''', (turma_id,))

    alunos = executar_query('''
    SELECT m.id as matricula_id, a.id as aluno_id, a.nome
    FROM matriculas m
    JOIN alunos a ON m.aluno_id = a.id
    WHERE m.turma_id = ?
    ''', (turma_id,))

    return render_template('notas/registrar.html',
                         turma=dict(turma),
                         modulos=[dict(m) for m in modulos] if modulos else [],
                         alunos=[dict(a) for a in alunos] if alunos else [])

# ============================================================================
# RELATÓRIOS
# ============================================================================

@app.route('/relatorios')
@login_requerido()
def relatorios():
    if not pode_ver_relatorios():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')
    return render_template('relatorios/index.html')

@app.route('/relatorio/turmas')
@login_requerido()
def relatorio_turmas():
    if not pode_ver_relatorios():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    turmas = executar_query('''
    SELECT t.*, c.nome as curso_nome, p.nome as professor_nome, COUNT(m.id) as total_alunos
    FROM turmas t
    JOIN cursos c ON t.curso_id = c.id
    JOIN professores p ON t.professor_id = p.id
    LEFT JOIN matriculas m ON t.id = m.turma_id
    GROUP BY t.id
    ''')

    return render_template('relatorios/turmas.html',
                         turmas=[dict(t) for t in turmas] if turmas else [])

@app.route('/relatorio/frequencia')
@login_requerido()
def relatorio_frequencia():
    if not pode_ver_relatorios():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    dados = executar_query('''
    SELECT a.nome, t.nome as turma, COUNT(*) as total_aulas,
           SUM(CASE WHEN f.presente = 1 THEN 1 ELSE 0 END) as presentes,
           ROUND(SUM(CASE WHEN f.presente = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as percentual
    FROM frequencias f
    JOIN matriculas m ON f.matricula_id = m.id
    JOIN alunos a ON m.aluno_id = a.id
    JOIN turmas t ON m.turma_id = t.id
    GROUP BY m.aluno_id, m.turma_id
    ORDER BY a.nome
    ''')

    return render_template('relatorios/frequencia.html',
                         dados=[dict(d) for d in dados] if dados else [])

@app.route('/relatorio/desempenho')
@login_requerido()
def relatorio_desempenho():
    if not pode_ver_relatorios():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    dados = executar_query('''
    SELECT a.nome, t.nome as turma, m.nome as modulo,
           n.primeira_nota, n.segunda_nota, n.terceira_nota, n.media_final
    FROM notas n
    JOIN matriculas mat ON n.matricula_id = mat.id
    JOIN alunos a ON mat.aluno_id = a.id
    JOIN turmas t ON mat.turma_id = t.id
    JOIN modulos m ON n.modulo_id = m.id
    ORDER BY a.nome, m.nome
    ''')

    return render_template('relatorios/desempenho.html',
                         dados=[dict(d) for d in dados] if dados else [])

@app.route('/relatorios/historico/<int:aluno_id>')
@login_requerido()
def historico_aluno(aluno_id):
    if session.get('tipo_usuario') == 'aluno' and session.get('usuario_id') != aluno_id:
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')
    if session.get('tipo_usuario') != 'aluno' and not pode_ver_relatorios():
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    aluno = executar_query('SELECT * FROM alunos WHERE id = ?', (aluno_id,), fetch_one=True)
    if not aluno:
        flash('Aluno não encontrado!', 'error')
        return redirect('/alunos')

    relatorios = executar_query('''
    SELECT * FROM relatorios_aluno WHERE aluno_id = ? ORDER BY data_criacao DESC
    ''', (aluno_id,))

    log = executar_query('''
    SELECT * FROM audit_log WHERE id_registro = ? ORDER BY data_acao DESC
    ''', (aluno_id,))

    return render_template('relatorios/historico.html',
                         aluno=dict(aluno),
                         relatorios=[dict(r) for r in relatorios] if relatorios else [],
                         log=[dict(l) for l in log] if log else [])

# ============================================================================
# ADMIN
# ============================================================================

@app.route('/admin')
@login_requerido()
def admin_dashboard():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    total_alunos = executar_query('SELECT COUNT(*) FROM alunos WHERE ativo = 1', fetch_one=True)[0] or 0
    total_professores = executar_query('SELECT COUNT(*) FROM professores WHERE ativo = 1', fetch_one=True)[0] or 0
    total_funcionarios = executar_query('SELECT COUNT(*) FROM funcionarios WHERE ativo = 1', fetch_one=True)[0] or 0
    total_turmas = executar_query('SELECT COUNT(*) FROM turmas WHERE ativa = 1', fetch_one=True)[0] or 0
    total_cursos = executar_query('SELECT COUNT(*) FROM cursos WHERE ativo = 1', fetch_one=True)[0] or 0
    receita = executar_query('SELECT SUM(valor_pago) FROM financeiro', fetch_one=True)[0] or 0

    return render_template('admin/dashboard.html',
                         total_alunos=total_alunos,
                         total_professores=total_professores,
                         total_funcionarios=total_funcionarios,
                         total_turmas=total_turmas,
                         total_cursos=total_cursos,
                         receita_total=float(receita) if receita else 0)

@app.route('/admin/funcionarios')
@login_requerido()
def listar_funcionarios():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    funcionarios = executar_query('''
    SELECT f.*, s.nome as setor_nome
    FROM funcionarios f
    LEFT JOIN setores s ON f.setor_id = s.id
    ORDER BY f.nome
    ''')

    return render_template('admin/funcionarios/listar.html',
                         funcionarios=[dict(f) for f in funcionarios] if funcionarios else [])

@app.route('/admin/funcionario/novo', methods=['GET', 'POST'])
@login_requerido()
def novo_funcionario():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        try:
            conexao = get_db()
            cursor = conexao.cursor()

            senha_temp = Autenticacao.gerar_senha_temporaria()

            cursor.execute('''
            INSERT INTO funcionarios (nome, email, cpf, senha, cargo, setor_id, salario)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (request.form.get('nome'), request.form.get('email'), request.form.get('cpf'),
                  Autenticacao.hash_senha(senha_temp), request.form.get('cargo'),
                  request.form.get('setor_id'), request.form.get('salario')))

            func_id = cursor.lastrowid

            cursor.execute('''
            INSERT INTO usuarios (email, senha, tipo_usuario, tabela_referencia, id_referencia)
            VALUES (?, ?, ?, ?, ?)
            ''', (request.form.get('email'), Autenticacao.hash_senha(senha_temp), 'funcionario', 'funcionarios', func_id))

            conexao.commit()
            conexao.close()

            flash(f'Funcionario criado! Senha: {senha_temp}', 'success')
            registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'CRIAR_FUNCIONARIO', 'funcionarios', func_id, {})
            return redirect('/admin/funcionarios')
        except Exception as e:
            flash(f'Erro: {str(e)}', 'error')

    setores = executar_query('SELECT * FROM setores')
    return render_template('admin/funcionarios/novo.html',
                         setores=[dict(s) for s in setores] if setores else [])

@app.route('/admin/cursos')
@login_requerido()
def listar_cursos():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    cursos = executar_query('''
    SELECT c.*, COUNT(DISTINCT t.id) as total_turmas
    FROM cursos c
    LEFT JOIN turmas t ON c.id = t.curso_id
    GROUP BY c.id ORDER BY c.nome
    ''')

    return render_template('admin/cursos/listar.html',
                         cursos=[dict(c) for c in cursos] if cursos else [])

@app.route('/admin/curso/novo', methods=['GET', 'POST'])
@login_requerido()
def novo_curso():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        if executar_update('''
        INSERT INTO cursos (nome, descricao, duracao_meses, valor)
        VALUES (?, ?, ?, ?)
        ''', (request.form.get('nome'), request.form.get('descricao'),
              request.form.get('duracao_meses'), request.form.get('valor'))):
            flash('Curso criado!', 'success')
            registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'CRIAR_CURSO', 'cursos', 1, {})
            return redirect('/admin/cursos')
        flash('Erro!', 'error')

    return render_template('admin/cursos/novo.html')

@app.route('/admin/modulos')
@login_requerido()
def listar_modulos():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    modulos = executar_query('''
    SELECT m.*, c.nome as curso_nome
    FROM modulos m
    JOIN cursos c ON m.curso_id = c.id
    ORDER BY c.nome, m.ordem
    ''')

    return render_template('admin/modulos/listar.html',
                         modulos=[dict(m) for m in modulos] if modulos else [])

@app.route('/admin/modulo/novo', methods=['GET', 'POST'])
@login_requerido()
def novo_modulo():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        if executar_update('''
        INSERT INTO modulos (curso_id, nome, descricao, carga_horaria, ordem)
        VALUES (?, ?, ?, ?, ?)
        ''', (request.form.get('curso_id'), request.form.get('nome'),
              request.form.get('descricao'), request.form.get('carga_horaria'),
              request.form.get('ordem'))):
            flash('Modulo criado!', 'success')
            registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'CRIAR_MODULO', 'modulos', 1, {})
            return redirect('/admin/modulos')
        flash('Erro!', 'error')

    cursos = executar_query('SELECT * FROM cursos WHERE ativo = 1 ORDER BY nome')
    return render_template('admin/modulos/novo.html',
                         cursos=[dict(c) for c in cursos] if cursos else [])

@app.route('/admin/setores')
@login_requerido()
def listar_setores():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    setores = executar_query('''
    SELECT s.*, COUNT(f.id) as total_funcionarios
    FROM setores s
    LEFT JOIN funcionarios f ON s.id = f.setor_id
    GROUP BY s.id ORDER BY s.nome
    ''')

    return render_template('admin/setores/listar.html',
                         setores=[dict(s) for s in setores] if setores else [])

@app.route('/admin/setor/novo', methods=['GET', 'POST'])
@login_requerido()
def novo_setor():
    if not pode_acessar('admin'):
        flash('Acesso negado!', 'error')
        return redirect('/dashboard')

    if request.method == 'POST':
        if executar_update('''
        INSERT INTO setores (nome, descricao)
        VALUES (?, ?)
        ''', (request.form.get('nome'), request.form.get('descricao'))):
            flash('Setor criado!', 'success')
            registrar_audit(session.get('usuario_id'), session.get('tipo_usuario'), 'CRIAR_SETOR', 'setores', 1, {})
            return redirect('/admin/setores')
        flash('Erro!', 'error')

    return render_template('admin/setores/novo.html')

if __name__ == '__main__':
    try:
        criar_banco_dados()
    except:
        pass

    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '5000'))

    print("\n" + "="*70)
    print("Sistema de Gestão Escolar v2.0")
    print("="*70)
    print(f"\nAcesse neste computador: http://localhost:{port}")
    print("Para acessar de outro computador, use o IP exibido pelo atalho.")
    print("Admin: admin@escola.com / Mudar@123")
    print("\n" + "="*70 + "\n")

    app.run(debug=False, host=host, port=port, threaded=True)
